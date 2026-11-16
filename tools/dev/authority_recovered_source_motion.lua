-- Private source-only motion session. Caller owns the sole onUpdate and keeps
-- the recovery controller active. No cross-process object identity is claimed.
local M={}
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(token(c.epoch) and token(c.generation) and token(c.nonce) and token(c.saved_nonce))
 assert(c.epoch~=c.generation and c.epoch~=c.nonce and c.epoch~=c.saved_nonce and c.nonce~=c.saved_nonce and c.generation~=c.saved_nonce and c.generation~=c.nonce)
 assert(c.nonce:sub(1,16)~=c.saved_nonce:sub(1,16))
 assert(type(c.baseline)=='number' and c.baseline%1==0 and c.baseline>=1 and c.baseline<=200000)
 for _,k in ipairs({'running','guard','register','bootstrap_factory','sampler_factory','ipc_factory','shutdown_factory','fault'})do
  assert(type(c[k])=='function',k..' required')
 end
 local failed=false;local busy=false;local staged;local bound={};local bootstrap,sampler,ipc,shutdown
 local function fail(reason)
  if not failed then failed=true;pcall(c.fault,reason)end
  return false
 end
 local function running()
  local ok,v=pcall(c.running);return ok and v==true
 end
 local function context()
  local ok,v=pcall(c.guard);return not failed and ok and v==true
 end
 local function active()return context() and running()end
 local function baseline(e,n)return active() and e==c.epoch and n==c.baseline end
 local function saved_guard(row,actor)
  return baseline(row.epoch,c.baseline) and row.classification=='saved_baseline' and bound[row.index]==actor
 end
 bootstrap=assert(c.bootstrap_factory({enabled=true,epoch=c.epoch,nonce=c.saved_nonce,baseline=c.baseline,
  guard=active,baseline_guard=baseline,complete=function(index,actor,sector)
   if not active() or staged or bound[index] then return false end
   staged={index=index,actor=actor,sector=sector};return true
  end}))
 sampler=assert(c.sampler_factory({enabled=true,epoch=c.epoch,generation=c.generation,nonce=c.nonce,
  guard=active,saved_baseline_limit=c.baseline,saved_baseline_guard=saved_guard,
  binding_guard=function()return false end,fault=function(reason)fail('sampler_'..tostring(reason))end}))
 local function route(value)
  if failed or type(value)~='string' then return false end
  local id=value:match('^([0-9a-f]+)|')
  if id and id==bootstrap:expected_request() then
   if not ipc:saved_request() or staged then return false end
   if bootstrap:event(value)~=true or bootstrap:state()~='idle' or not staged then return false end
   local item=staged;staged=nil
   if ipc:saved_request()~=item.index or bound[item.index] or not active() then return false end
   bound[item.index]=item.actor
   if sampler:register({epoch=c.epoch,index=item.index,classification='saved_baseline'},item.actor)~=true then return false end
   return ipc:saved_registered(item.index)==true
  elseif id and id==sampler:expected_request() then
   if not ipc:requested() then return false end
   local ok,sample=sampler:event(value)
   return ok==true and ipc:complete(sample)==true
  end
  return false
 end
 shutdown=assert(c.shutdown_factory({enabled=true,bootstrap=bootstrap,sampler=sampler,guard=context,
  quiescent=function()return not staged and not bootstrap:expected_request() and not sampler:expected_request() end,
  route=route,fault=function(reason)fail('router_'..tostring(reason))end}))
 ipc=assert(c.ipc_factory({saved_baseline={limit=c.baseline,guard=baseline},
  guard=active,stop=function()return shutdown:stop()end,fault=function(reason)fail('ipc_'..tostring(reason))end}))
 assert(c.register(function(value)
  if shutdown:event(value)~=true then fail('event')end
 end)==true)
 assert(ipc:start()==true)
 local api={}
 function api:tick()
  if busy or failed then return fail('state')end
  busy=true
  local ok=pcall(function()
   assert(context() and shutdown:check())
   if ipc:state()=='stopped' then assert(shutdown:state()=='stopped' and ipc:check_stopped());return end
   assert(active() and shutdown:state()=='active')
   assert(ipc:tick()==true)
   if ipc:state()=='stopped' then assert(shutdown:state()=='stopped' and ipc:check_stopped());return end
   assert(bootstrap:tick()==true)
   if ipc:saved_request() and bootstrap:state()=='idle' and not staged then
    assert(bootstrap:begin(ipc:saved_request())==true)
   end
   if ipc:requested() then
    assert(sampler:tick()==true)
    if sampler:state()=='ready' then assert(ipc:complete(nil)==true)end
   end
  end)
  busy=false;if not ok then return fail('tick')end;return true
 end
 function api:state()return failed and 'failed' or (ipc:state()=='stopped' and 'stopped' or 'active')end
 return api
end

function M.new_x4(c)
 assert(type(c)=='table' and type(c.expected_save_path)=='string' and type(c.port)=='number')
 local ffi=require('ffi');ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local netlib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
 local net=assert(netlib.open('127.0.0.1',c.port))
 local function environment()
  local p=C.GetSaveFolderPath()
  return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==c.expected_save_path and
   C.IsPlayerValid() and type(X4LAN_AUTHORITY_RECOVERY_READY)=='function' and X4LAN_AUTHORITY_RECOVERY_READY()==true
 end
 return M.new({enabled=true,epoch=c.epoch,generation=c.generation,nonce=c.nonce,saved_nonce=c.saved_nonce,
  baseline=c.baseline,running=function()return not C.IsGamePaused()end,guard=environment,
  register=function(f)return RegisterEvent('X4AuthorityJobDescriptorProbe.Result',function(_,value)f(value)end)~=false end,
  bootstrap_factory=function(o)
   o.timeout=c.timeout;o.expected_save_path=c.expected_save_path;o.resolve=X4LAN_RESOLVE_STRING
   return X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP.new_x4(o)
  end,
  sampler_factory=function(o)
   o.expected_save_path=c.expected_save_path;o.resolve=X4LAN_RESOLVE_STRING;o.descriptor=X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE
   o.max_tracks=1;o.scan_budget=1;o.interval=.1;o.timeout=c.timeout;o.min_dt=.02;o.max_dt=1
   return X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER.new_x4(o)
  end,
  ipc_factory=function(o)
   o.enabled=true;o.lease=c.lease;o.attempt=c.attempt;o.epoch=c.epoch;o.generation=c.generation
   o.timeout=c.timeout;o.clock=GetCurRealTime;o.net=net
   return X4LAN_AUTHORITY_SOURCE_MOTION_IPC.new(o)
  end,shutdown_factory=X4LAN_SOURCE_MOTION_SHUTDOWN.new,
  fault=function(reason)DebugError('[X4LAN] AUTH_RECOVERED_SOURCE ERROR '..tostring(reason))end})
end
X4LAN_RECOVERED_SOURCE_MOTION=M
return M
