-- Private once-only read-only client motion probe. The existing participant
-- update owner calls tick; process, FD, checkpoint and STOPPED are external.
local M={}
local player_sector_event_claimed=false
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 local fixed={};for k,v in pairs(c)do fixed[k]=v end;c=fixed
 for _,name in ipairs({'guard','running','router_factory','owner_factory','fault'})do assert(type(c[name])=='function',name)end
 local failed,busy=false,false;local router,owner,sector_reader
 local sector_phase,sector_staged,bound_ready='disabled',nil,nil
 local function fail(reason)
  if not failed then failed=true;pcall(c.fault,reason)end
  return false
 end
 local function context()
  local ok,v=pcall(c.guard);return not failed and ok and v==true
 end
 local function stop_sector_reader()
  if sector_phase=='disabled' then return true end
  if sector_phase~='done' then return false end
  local ok,closed=pcall(sector_reader.close,sector_reader)
  if not ok or closed~=true or sector_reader:state()~='closed' or not context() then return false end
  sector_phase='closed';return true
 end
 router=assert(c.router_factory({guard=context,fault=function()fail('router')end}))
 assert(router:start() and context())
 owner=assert(c.owner_factory({router=router,guard=context,stop=function()
  return context() and c.running()==true and router:state()=='active' and stop_sector_reader()
 end,fault=function()fail('owner')end}))
 if c.player_sector==nil then
  assert(router:attach(c.router_generation,c.nonce,c.epoch,owner) and owner:start() and context())
 else
  assert(router:attach(c.router_generation,c.nonce,c.epoch,owner) and context())
  local p=c.player_sector
  assert(type(p)=='table' and token(c.epoch) and token(p.incarnation) and token(p.nonce) and
   c.epoch~=p.incarnation and c.epoch~=p.nonce and p.incarnation~=p.nonce and
   type(p.factory)=='function' and type(p.register)=='function' and type(p.report)=='function' and
   (p.after_bound==nil or (p.after_bound==true and type(p.bound_ready)=='function')))
  local incarnation,nonce,factory,register,report=p.incarnation,p.nonce,p.factory,p.register,p.report
  bound_ready=p.after_bound and p.bound_ready or nil
  sector_phase=bound_ready and 'waiting_bound' or 'idle'
  local function sector_guard(value)
   if value~=incarnation or not context() then return false end
   local ok,running=pcall(c.running)
   local status,phase=pcall(owner.state,owner)
   return ok and running==true and status and phase~='stopped' and context()
  end
  sector_reader=assert(factory({epoch=c.epoch,incarnation=incarnation,nonce=nonce,guard=sector_guard,
   complete=function(result)
    if sector_phase~='pending' or sector_staged~=nil or type(result)~='table' or getmetatable(result)~=nil or
     result.epoch~=c.epoch or result.incarnation~=incarnation or result.sequence~=1 or
     type(result.sector_macro)~='string' or not result.sector_macro:match('^[A-Za-z0-9_]+$') or
     #result.sector_macro>128 then return false end
    for key in pairs(result)do if key~='epoch' and key~='incarnation' and key~='sequence' and key~='sector_macro' then return false end end
    sector_staged={epoch=result.epoch,incarnation=result.incarnation,sequence=result.sequence,sector_macro=result.sector_macro}
    return true
   end}))
  assert(type(sector_reader.begin)=='function' and type(sector_reader.event)=='function' and
   type(sector_reader.tick)=='function' and type(sector_reader.state)=='function' and type(sector_reader.close)=='function')
  assert(register(function(value)
   if busy or failed or sector_phase~='pending' then return fail('sector_event')end
   busy=true
   local ok=pcall(function()
    assert(sector_guard(incarnation) and sector_reader:event(value)==true and
     sector_reader:state()=='idle' and sector_staged and sector_guard(incarnation))
    local staged=sector_staged;local macro=staged.sector_macro
    assert(report(staged)==true and sector_guard(incarnation) and sector_reader:state()=='idle' and
     getmetatable(staged)==nil and staged.epoch==c.epoch and staged.incarnation==incarnation and
     staged.sequence==1 and staged.sector_macro==macro)
    for key in pairs(staged)do assert(key=='epoch' or key=='incarnation' or key=='sequence' or key=='sector_macro')end
    sector_staged=nil;sector_phase='done'
   end)
   busy=false;if not ok then return fail('sector_event')end;return true
  end)==true and context())
  assert(owner:start() and context())
 end
 local api={}
 function api:tick()
  if busy or failed then return fail('state')end
  busy=true
  local ok=pcall(function()
   assert(context() and router:state()=='active')
   local phase=owner:state()
   assert(phase=='stopped' or c.running()==true)
   assert(owner:tick()==true and context() and router:state()=='active')
   if sector_reader then
    if sector_phase=='waiting_bound' then
     local checked,ready=pcall(bound_ready)
     assert(checked and type(ready)=='boolean' and context())
     if ready then sector_phase='idle' end
    end
    if sector_phase=='idle' then
     assert(owner:state()~='stopped' and c.running()==true)
     sector_phase='pending';assert(sector_reader:begin()==true)
    elseif sector_phase=='pending' then assert(sector_reader:tick()==true)
    else assert(sector_phase=='waiting_bound' or sector_phase=='done' or sector_phase=='closed')end
   end
  end)
  busy=false;if not ok then return fail('tick')end;return true
 end
 function api:state()return failed and 'failed' or owner:state()end
 return api
end
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 local fixed={};for k,v in pairs(c)do fixed[k]=v end;c=fixed
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
 local sector_config
 if c.player_sector~=nil then
  local p=c.player_sector
  assert(type(p)=='table' and getmetatable(p)==nil and token(p.incarnation) and token(p.nonce))
  for key in pairs(p)do assert(key=='incarnation' or key=='nonce' or key=='after_bound')end
  assert(p.after_bound==nil or p.after_bound==true)
  assert(p.incarnation~=p.nonce and not seen[p.incarnation] and not seen[p.nonce])
  sector_config={incarnation=p.incarnation,nonce=p.nonce,after_bound=p.after_bound}
  assert(type(X4LAN_PLAYER_SECTOR_INTEREST)=='table' and type(X4LAN_PLAYER_SECTOR_INTEREST.new_x4)=='function')
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
 -- This one-shot diagnostic accepts one BIND. Ordinary motion is unchanged.
 local bound_phase=sector_config and sector_config.after_bound and 'waiting_bind' or nil
 local expected_bound
 local checked_net={send=function(_,value)
  if bound_phase and type(value)=='string' and value:sub(1,2)=='R|' then
   local fields={};for item in (value..'|'):gmatch('(.-)|')do fields[#fields+1]=item end
   if fields[4]=='BOUND' then
    assert(bound_phase=='waiting_ack' and value==expected_bound)
    local sent=net:send(value)
    if sent==true then bound_phase='sent' end
    return sent
   end
  end
  return net:send(value)
 end,receive=function()
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
   if bound_phase then
    assert(bound_phase=='waiting_bind')
    expected_bound=table.concat({'R',c.lease,c.attempt,'BOUND',unpack(fields,5,11)},'|')
    bound_phase='waiting_ack'
   end
  else assert(fields[4]=='STOP' and #fields==7)end
  return value
 end}
 local player_sector
 if sector_config then
  player_sector={incarnation=sector_config.incarnation,nonce=sector_config.nonce,
   factory=function(o)
    o.enabled=true;o.timeout=c.timeout;o.expected_save_path=c.expected_save_path;o.resolve=X4LAN_RESOLVE_STRING
    return X4LAN_PLAYER_SECTOR_INTEREST.new_x4(o)
   end,
   register=function(callback)
    assert(not player_sector_event_claimed);player_sector_event_claimed=true
    return RegisterEvent('X4AuthorityPlayerSectorInterest.Result',function(_,value)callback(value)end)~=false
   end,
   report=function(result)
    DebugError('[X4LAN] AUTH_CLIENT_SECTOR observed sector='..result.sector_macro)
    return true
   end}
  if sector_config.after_bound then
   player_sector.after_bound=true
   player_sector.bound_ready=function()return bound_phase=='sent'end
  end
 end
 return M.new({enabled=true,epoch=c.epoch,nonce=c.nonce,router_generation=c.router_generation,player_sector=player_sector,
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
