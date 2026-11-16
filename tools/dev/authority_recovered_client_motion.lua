-- Private once-only read-only client motion probe. The existing participant
-- update owner calls tick; process, FD, checkpoint and STOPPED are external.
local M={}
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 local fixed={};for k,v in pairs(c)do fixed[k]=v end;c=fixed
 for _,name in ipairs({'guard','running','router_factory','owner_factory','fault'})do assert(type(c[name])=='function',name)end
 local failed,busy=false,false;local router,owner
 local function fail(reason)
  if not failed then failed=true;pcall(c.fault,reason)end
  return false
 end
 local function context()
  local ok,v=pcall(c.guard);return not failed and ok and v==true
 end
 router=assert(c.router_factory({guard=context,fault=function()fail('router')end}))
 assert(router:start() and context())
 owner=assert(c.owner_factory({router=router,guard=context,stop=function()
  return context() and c.running()==true and router:state()=='active'
 end,fault=function()fail('owner')end}))
 assert(router:attach(c.router_generation,c.nonce,c.epoch,owner) and owner:start() and context())
 local api={}
 function api:tick()
  if busy or failed then return fail('state')end
  busy=true
  local ok=pcall(function()
   assert(context() and router:state()=='active')
   local phase=owner:state()
   assert(phase=='stopped' or c.running()==true)
   assert(owner:tick()==true and context() and router:state()=='active')
  end)
  busy=false;if not ok then return fail('tick')end;return true
 end
 function api:state()return failed and 'failed' or owner:state()end
 return api
end
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 local fixed={};for k,v in pairs(c)do fixed[k]=v end;c=fixed
 local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
 local function integer(v)return type(v)=='number' and v==v and v%1==0 end
 assert(type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save' and
  integer(c.port) and c.port>=1 and c.port<=65535 and integer(c.baseline) and c.baseline>=1 and c.baseline<=200000 and
  type(c.timeout)=='number' and c.timeout==c.timeout and c.timeout>0 and c.timeout<=30)
 local allowed={};local locked
 if c.indices==nil then
  assert(integer(c.index) and c.index>=1 and c.index<=c.baseline)
  locked=string.format('%.0f',c.index);allowed[locked]=true
 else
  assert(c.index==nil and type(c.indices)=='table' and getmetatable(c.indices)==nil and #c.indices>=1 and #c.indices<=32)
  local count=0
  for k in pairs(c.indices)do assert(integer(k) and k>=1 and k<=#c.indices);count=count+1 end
  assert(count==#c.indices)
  for i=1,count do
   local n=c.indices[i];assert(integer(n) and n>=1 and n<=c.baseline)
   local key=string.format('%.0f',n);assert(not allowed[key]);allowed[key]=true
  end
 end
 local seen={}
 for _,key in ipairs({'lease','attempt','epoch','generation','nonce','router_generation'})do
  local v=c[key];assert(token(v) and not seen[v]);seen[v]=true
 end
 local ffi=require('ffi');ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local netlib=X4LAN_LOCAL_UDP_MODULE.load(ffi.os,package.loadlib)
 local net=assert(netlib.open('127.0.0.1',c.port))
 assert(type(net.pending)=='function')
 local function environment()
  local p=C.GetSaveFolderPath()
  return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==c.expected_save_path and
   C.IsPlayerValid() and type(X4LAN_RECOVERED_CLIENT_LOAD_READY)=='function' and X4LAN_RECOVERED_CLIENT_LOAD_READY()==true
 end
 -- At most one permitted saved ship is in scope. With a candidate list the
 -- first correlated BIND seals the index; an invalid attempt faults the owner.
 local checked_net={send=function(_,value)return net:send(value)end,receive=function()
  local pending=net:pending();assert(type(pending)=='boolean')
  -- Do not consume an arrival racing with a negative readability check:
  -- invalid datagrams return nil from receive and must remain for next tick.
  if not pending then return nil end
  local value=net:receive()
  assert(value~=nil)
  assert(type(value)=='string' and #value<=768)
  local fields={};for item in (value..'|'):gmatch('(.-)|')do fields[#fields+1]=item end
  assert(fields[1]=='M' and fields[2]==c.lease and fields[3]==c.attempt)
  if fields[4]=='BIND' then
   assert(#fields==18 and token(fields[5]) and fields[6]==c.epoch and fields[7]==c.generation and allowed[fields[8]])
   if locked==nil then locked=fields[8]end
   assert(fields[8]==locked)
  else assert(fields[4]=='STOP' and #fields==7)end
  return value
 end}
 return M.new({enabled=true,epoch=c.epoch,nonce=c.nonce,router_generation=c.router_generation,
  guard=environment,running=function()return not C.IsGamePaused()end,
  router_factory=function(o)
   return X4LAN_CLIENT_MOTION_EVENT_ROUTER.new_x4({enabled=true,max_generations=1,max_tracks=1,
    guard=o.guard,retire_guard=function()return false end,fault=o.fault})
  end,
  owner_factory=function(o)
   return X4LAN_MOTION_CLIENT_OWNER.new_x4({enabled=true,net=checked_net,lease=c.lease,attempt=c.attempt,
    epoch=c.epoch,generation=c.generation,nonce=c.nonce,router_generation=c.router_generation,event_router=o.router,
    timeout=c.timeout,max_age=c.timeout,max_tracks=1,expected_save_path=c.expected_save_path,
    resolve=X4LAN_RESOLVE_STRING,binding=X4LAN_REPLICA_MOTION_BINDING,buffer=X4LAN_MOTION_BUFFER,
    saved_baseline={enabled=true,baseline=c.baseline,binding=X4LAN_SAVED_BASELINE_MOTION_BINDING,
     guard=function(e,n)return environment() and not C.IsGamePaused() and e==c.epoch and n==c.baseline end},
    guard=o.guard,stop=o.stop,fault=o.fault})
  end,
  fault=function()DebugError('[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR')end})
end
X4LAN_RECOVERED_CLIENT_MOTION=M
return M
