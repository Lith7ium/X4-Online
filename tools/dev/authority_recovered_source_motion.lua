-- Private source-only motion session. Caller owns the sole onUpdate and keeps
-- the recovery controller active. No cross-process object identity is claimed.
local M={}
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function exact(value,expected)
 if type(value)~='table' or getmetatable(value)~=nil then return false end
 for k,v in pairs(value)do if rawget(expected,k)~=v then return false end end
 for k,v in pairs(expected)do if rawget(value,k)~=v then return false end end
 return true
end
local function copy_result(value,depth)
 if type(value)~='table' then return value end
 assert(depth>0 and getmetatable(value)==nil)
 local copy={};for k,v in pairs(value)do copy[k]=copy_result(v,depth-1)end
 return copy
end
local function equal_result(value,expected,depth)
 if type(expected)~='table' then return value==expected end
 if depth<=0 or type(value)~='table' or getmetatable(value)~=nil then return false end
 for k,v in pairs(value)do if not equal_result(v,rawget(expected,k),depth-1)then return false end end
 for k,v in pairs(expected)do if not equal_result(rawget(value,k),v,depth-1)then return false end end
 return true
end
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(token(c.epoch) and token(c.generation) and token(c.nonce) and token(c.saved_nonce))
 assert(c.epoch~=c.generation and c.epoch~=c.nonce and c.epoch~=c.saved_nonce and c.nonce~=c.saved_nonce and c.generation~=c.saved_nonce and c.generation~=c.nonce)
 assert(c.nonce:sub(1,16)~=c.saved_nonce:sub(1,16))
 assert(type(c.baseline)=='number' and c.baseline%1==0 and c.baseline>=1 and c.baseline<=200000)
 for _,k in ipairs({'running','guard','register','bootstrap_factory','sampler_factory','ipc_factory','shutdown_factory','fault'})do
  assert(type(c[k])=='function',k..' required')
 end
 local failed=false;local busy=false;local staged;local bound={};local bootstrap,sampler,ipc,shutdown,selector
 local pair_settings,pair,pair_done
 if c.local_pair~=nil then
  local p=c.local_pair
  assert(type(p)=='table' and token(p.nonce) and type(p.index)=='number' and p.index%1==0 and
   p.index>=1 and p.index<=c.baseline and type(p.factory)=='function' and type(p.report)=='function')
  assert(type(c.clock)=='function' and type(c.timeout)=='number' and c.timeout>0 and c.timeout<=120)
  assert(p.nonce~=c.epoch and p.nonce~=c.generation and p.nonce~=c.nonce and p.nonce~=c.saved_nonce and
   p.nonce:sub(1,16)~=c.nonce:sub(1,16) and p.nonce:sub(1,16)~=c.saved_nonce:sub(1,16))
  pair_settings={nonce=p.nonce,index=p.index,factory=p.factory,report=p.report}
 end
 local route_failure
 local selection=c.selection;local selected,reported=nil,false;local allowed={}
 if selection~=nil then
  assert(type(selection)=='table' and token(selection.nonce) and type(selection.factory)=='function' and
   type(selection.register)=='function' and type(selection.report)=='function' and type(selection.candidates)=='table')
  assert(selection.nonce~=c.epoch and selection.nonce~=c.generation and selection.nonce~=c.nonce and selection.nonce~=c.saved_nonce and
   selection.nonce:sub(1,16)~=c.nonce:sub(1,16) and selection.nonce:sub(1,16)~=c.saved_nonce:sub(1,16))
  if pair_settings then assert(selection.nonce:sub(1,16)~=pair_settings.nonce:sub(1,16))end
  local fixed={};for k,v in pairs(selection)do fixed[k]=v end
  assert(#selection.candidates>=1 and #selection.candidates<=32);fixed.candidates={}
  for i,n in ipairs(selection.candidates)do
   assert(type(n)=='number' and n==n and n%1==0 and n>=1 and n<=c.baseline and not allowed[n])
   allowed[n]=true;fixed.candidates[i]=n
  end
  local entries=0;for k in pairs(selection.candidates)do
   assert(type(k)=='number' and k%1==0 and k>=1 and k<=#selection.candidates);entries=entries+1
  end
  assert(entries==#selection.candidates and #fixed.candidates==entries)
  selection=fixed
 end
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
  route_failure=nil
  local function reject(reason)
   route_failure=reason
   return false
  end
  if failed or type(value)~='string' then
   return reject('route_input')
  end
  local id=value:match('^([0-9a-f]+)|')
  if pair_settings and value:sub(1,16)==pair_settings.nonce:sub(1,16) then
   if not pair or pair_done or not ipc:requested() or pair:event(value)~=true then
    return reject('local_pair_event')
   end
   return true
  end
  if id and id==bootstrap:expected_request() then
   if not ipc:saved_request() or staged then
    return reject('bootstrap_request')
   end
   if bootstrap:event(value)~=true then
    local detail=type(bootstrap.diagnostic)=='function' and bootstrap:diagnostic() or nil
    local allowed={guard=true,format=true,correlation=true,names=true,parse_or_guard=true,md_unavailable=true,
     inspect_before=true,complete=true,inspect_after=true}
    return reject(allowed[detail] and 'bootstrap_'..detail or 'bootstrap_response')
   end
   if bootstrap:state()~='idle' or not staged then
    return reject('bootstrap_completion')
   end
   local item=staged;staged=nil
   if ipc:saved_request()~=item.index or bound[item.index] or not active() then
    return reject('bootstrap_binding')
   end
   bound[item.index]=item.actor
   if sampler:register({epoch=c.epoch,index=item.index,classification='saved_baseline'},item.actor)~=true then
    return reject('sampler_register')
   end
   if ipc:saved_registered(item.index)~=true then
    return reject('ipc_saved_registration')
   end
   return true
  elseif id and id==sampler:expected_request() then
   if not ipc:requested() then
    return reject('sampler_request')
   end
   local ok,sample=sampler:event(value)
   if ok~=true then
    return reject('sampler_response')
   end
   if ipc:complete(sample)~=true then
    return reject('ipc_sample_completion')
   end
   return true
  end
  return reject('unknown_request')
 end
 shutdown=assert(c.shutdown_factory({enabled=true,bootstrap=bootstrap,sampler=sampler,guard=context,
  quiescent=function()return not staged and not bootstrap:expected_request() and not sampler:expected_request() and
   (not pair or (pair_done and pair:state()=='stopped')) and
   (not selector or selector:state()=='done') end,
  route=route,fault=function(reason)
   if reason=='event' then
    local phase=type(shutdown.diagnostic)=='function' and shutdown:diagnostic() or nil
    local allowed={guard_before=true,route=true,guard_after=true}
    local detail=(phase=='route' and route_failure) or (allowed[phase] and phase) or 'unknown'
    fail('router_event_'..detail)
   else
    fail('router_'..tostring(reason))
   end
  end}))
 ipc=assert(c.ipc_factory({saved_baseline={limit=c.baseline,guard=baseline},
  candidate_enabled=selection~=nil,guard=active,stop=function()return shutdown:stop()end,fault=function(reason)fail('ipc_'..tostring(reason))end}))
 assert(c.register(function(value)
  if shutdown:event(value)~=true then fail('event')end
 end)==true)
 if selection then
  selector=assert(selection.factory({enabled=true,epoch=c.epoch,nonce=selection.nonce,baseline=c.baseline,
   candidates=selection.candidates,guard=active,baseline_guard=baseline}))
  assert(selection.register(function(value)
   if busy or failed or not selector or selector:state()~='waiting' or ipc:state()=='stopped' or selector:event(value)~=true then
    fail('candidate_event')
   end
  end)==true)
 end
 assert(ipc:start()==true)
 if selector then assert(selector:start()==true)end
 local api={}
 function api:tick()
  if busy or failed then return fail('state')end
  busy=true
  local ok=pcall(function()
   assert(context() and shutdown:check())
   if ipc:state()=='stopped' then assert(shutdown:state()=='stopped' and ipc:check_stopped());return end
   assert(active() and shutdown:state()=='active')
   if selector and not reported then
    if selector:state()=='waiting' then assert(selector:tick()==true)end
    if selector:state()=='done' and ipc:candidate_requested() then
     local result=assert(selector:result())
     local report
     if result.status=='candidate' then
      assert(result.epoch==c.epoch and allowed[result.index] and result.runtime_reservation==false)
      selected=result.index;report={status='candidate',epoch=c.epoch,index=selected,runtime_reservation=false}
     else
      assert(result.status=='inconclusive' and (result.reason=='no_candidate' or result.reason=='registry_refused' or result.reason=='getter_or_context_unavailable'))
      report={status='inconclusive',reason=result.reason}
     end
     assert(exact(result,report))
     local expected={};for k,v in pairs(report)do expected[k]=v end
     assert(selection.report(report)==true and exact(report,expected) and exact(result,expected) and
      selector:state()=='done' and context() and active())
     assert(ipc:candidate_complete(report)==true);reported=true
    else assert(selector:state()=='waiting' or selector:state()=='done')end
   end
   assert(ipc:tick()==true)
   if ipc:state()=='stopped' then assert(shutdown:state()=='stopped' and ipc:check_stopped());return end
   assert(bootstrap:tick()==true)
   if ipc:saved_request() and bootstrap:state()=='idle' and not staged then
    if selector then assert(reported and selected and ipc:saved_request()==selected)end
    assert(bootstrap:begin(ipc:saved_request())==true)
   end
   if ipc:requested() then
    if pair_settings and not pair_done then
     if not pair then
      local count=0;for _ in pairs(bound)do count=count+1 end
      local actor=bound[pair_settings.index]
      assert(count==1 and actor and (not selector or selected==pair_settings.index))
      local pair_guard=function()return active() and ipc:requested() and bound[pair_settings.index]==actor end
      local pair_sampler=assert(c.sampler_factory({enabled=true,epoch=c.epoch,generation=c.generation,
       nonce=pair_settings.nonce,guard=pair_guard,saved_baseline_limit=c.baseline,
       saved_baseline_guard=saved_guard,binding_guard=function()return false end,
       fault=function(reason)fail('local_pair_sampler_'..tostring(reason))end}))
      assert(pair_sampler~=sampler)
      pair=assert(pair_settings.factory({enabled=true,sampler=pair_sampler,epoch=c.epoch,
       generation=c.generation,index=pair_settings.index,actor=actor,timeout=c.timeout,
       clock=c.clock,guard=pair_guard,fault=function(reason)fail('local_pair_'..tostring(reason))end}))
      assert(pair:start()==true)
     end
     if pair:state()=='reading' then assert(pair:tick()==true)end
     if pair:state()=='done' then
      local result=assert(pair:result());local expected=copy_result(result,4)
      assert(pair_settings.report(result)==true and equal_result(result,expected,4) and
       pair:state()=='done' and active() and ipc:requested())
      assert(pair:stop()==true and pair:state()=='stopped');pair_done=true
     end
    end
    if not pair_settings or pair_done then
     assert(sampler:tick()==true)
     if sampler:state()=='ready' then assert(ipc:complete(nil)==true)end
    end
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
 assert(type(net.pending)=='function')
 -- receive() returns nil both for an empty queue and after consuming an empty
 -- or oversized datagram. Check readiness first so malformed packets fault.
 -- A packet arriving after a negative check stays queued for the next tick.
 local checked_net={
  send=function(_,value)return net:send(value)end,
  pending=function()return net:pending()end,
  receive=function()
   local pending=net:pending();assert(type(pending)=='boolean')
   if not pending then return nil end
   local value=net:receive();assert(value~=nil)
   return value
  end,
 }
 local function environment()
  local p=C.GetSaveFolderPath()
  return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==c.expected_save_path and
   C.IsPlayerValid() and type(X4LAN_AUTHORITY_RECOVERY_READY)=='function' and X4LAN_AUTHORITY_RECOVERY_READY()==true
 end
 local selection
 if c.selection~=nil then
  local s=c.selection
  assert(type(s)=='table' and type(X4LAN_AUTHORITY_REGISTRY_MOTION_CANDIDATE)=='table')
  assert(s.nonce~=c.lease and s.nonce~=c.attempt)
  selection={nonce=s.nonce,candidates=s.candidates,report=function()return true end,
   register=function(f)return RegisterEvent('X4AuthorityRegistryMotionCandidate.Result',function(_,value)f(value)end)~=false end,
   factory=function(o)
    o.timeout=c.timeout;o.expected_save_path=c.expected_save_path;o.resolve=X4LAN_RESOLVE_STRING
    return X4LAN_AUTHORITY_REGISTRY_MOTION_CANDIDATE.new_x4(o)
   end}
 end
 local local_pair
 if c.local_pair~=nil then
  local p=c.local_pair
  assert(type(p)=='table' and token(p.nonce) and type(p.index)=='number' and p.index%1==0 and
   p.index>=1 and p.index<=c.baseline and p.nonce~=c.lease and p.nonce~=c.attempt)
  for k in pairs(p)do assert(k=='nonce' or k=='index')end
  assert(type(X4LAN_AUTHORITY_SOURCE_MOTION_LOCAL_PAIR)=='table' and
   type(X4LAN_AUTHORITY_SOURCE_MOTION_LOCAL_PAIR.new)=='function')
  local_pair={nonce=p.nonce,index=p.index,factory=X4LAN_AUTHORITY_SOURCE_MOTION_LOCAL_PAIR.new,
   report=function(result)
    if result.status=='unavailable' and result.reason=='frame_interval_or_rate' then
     DebugError('[X4LAN] AUTH_LOCAL_PAIR unavailable')
    elseif result.status=='estimated' then
     local a,b,v=result.first,result.second,result.velocity
     assert(type(a)=='table' and type(b)=='table' and type(v)=='table')
     DebugError(('[X4LAN] AUTH_LOCAL_PAIR estimated dt=%.17g vx=%.17g vy=%.17g vz=%.17g'):
      format(b.source_time-a.source_time,v.x,v.y,v.z))
    else return false end
    return true
   end}
 end
 return M.new({enabled=true,epoch=c.epoch,generation=c.generation,nonce=c.nonce,saved_nonce=c.saved_nonce,selection=selection,
  local_pair=local_pair,clock=GetCurRealTime,timeout=c.timeout,
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
   o.timeout=c.timeout;o.clock=GetCurRealTime;o.net=checked_net
   return X4LAN_AUTHORITY_SOURCE_MOTION_IPC.new(o)
  end,shutdown_factory=X4LAN_SOURCE_MOTION_SHUTDOWN.new,
  fault=function(reason)DebugError('[X4LAN] AUTH_RECOVERED_SOURCE ERROR '..tostring(reason))end})
end
X4LAN_RECOVERED_SOURCE_MOTION=M
return M
