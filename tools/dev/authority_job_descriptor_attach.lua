-- Disposable diagnostic. The existing load probe is the sole onUpdate owner.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_job_attach~=true or cfg.authority_job_descriptor~=true then return end
local ffi=require('ffi');local C=ffi.C
local epoch,run=cfg.authority_job_registry_epoch,cfg.authority_ticket.world_epoch
assert(type(epoch)=='string' and #epoch==32 and epoch:match('^[0-9a-f]+$'))
assert(type(run)=='string' and #run==32 and run:match('^[0-9a-f]+$') and run~=epoch)
assert(type(Pause)=='function' and type(Unpause)=='function' and type(RegisterEvent)=='function')
local phase='new';local app,descriptor,failed,start,last,settled=nil,nil,false,nil,nil,nil
local sampled=false
local function log(s) DebugError('[X4LAN] AUTH_JOB_ATTACH '..s) end
local function desc_log(s) DebugError('[X4LAN] AUTH_JOB_DESCRIPTOR '..s) end
local function fail()
 if not failed then
  failed=true;phase='failed'
  if descriptor then pcall(function() descriptor:abort() end) end
  log('ERROR')
 end
end
local function guard()
 local p=C.GetSaveFolderPath()
 assert(p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_load_save_path)
 assert(C.IsPlayerValid())
 local t=GetCurRealTime();assert(type(t)=='number' and t==t and t>=0 and t<math.huge and (not last or t>=last))
 start=start or t;last=t;assert(t-start<=cfg.authority_job_window+45)
 return t,C.IsGamePaused()
end
local function report(row,actor)
 assert(phase=='running' and row.epoch==epoch and row.birth_confirmed==false and row.delivery_confirmed==false)
 assert(row.classification=='previously_observed' or row.classification=='previously_unobserved_existing_index' or row.classification=='new_registry_entry')
 log(('EVENT sequence=%.0f index=%.0f class=%s'):format(row.sequence,row.index,row.classification))
 if row.classification=='new_registry_entry' and not sampled then
  assert(not descriptor and actor~=nil);phase='descriptor'
  descriptor=assert(X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE.new_x4({enabled=true,epoch=epoch,request_id=run,
   timeout=5,row=row,actor=actor,expected_save_path=cfg.authority_load_save_path,
   guard=function() return not failed and phase=='descriptor' and app:state()~='failed' end}))
  assert(descriptor:start())
 end
 return true
end
local function done(row)
 assert(phase=='running' and sampled and row.registry_mode=='attached' and row.baseline_count==10054 and row.baseline_known_count==0)
 assert(row.birth_confirmed==false and row.delivery_confirmed==false and row.coverage=='unknown')
 assert(row.classification=='local_activations_observed')
 log(('SUMMARY observed=%.0f acknowledged=%.0f baseline=%.0f class=%s'):format(row.observed,row.acknowledged,row.baseline_count,row.classification))
 phase='pause_request';return true
end
RegisterEvent('X4AuthorityJobDescriptorProbe.Result',function(_,value)
 if failed then return end
 local ok=pcall(function()
  assert(phase=='descriptor' and descriptor and not sampled)
  local accepted,row=descriptor:response(value)
  assert(accepted and type(row)=='table' and row.descriptor_atomic==false and row.birth_confirmed==false and row.delivery_confirmed==false)
  desc_log(('SAMPLE request=%s epoch=%s sequence=%.0f index=%.0f macro=%s owner=%s sector_macro=%s x=%.17g y=%.17g z=%.17g game_before_request=%.17g game_before_pose=%.17g game_after_pose=%.17g'):format(
   run,row.epoch,row.sequence,row.index,row.macro,row.owner,row.sector_macro,row.x,row.y,row.z,row.game_before_request,row.game_before_pose,row.game_after_pose))
  sampled=true;descriptor:close();descriptor=nil;phase='running'
 end)
 if not ok then fail() end
end)
function X4LAN_JOB_ATTACH_UPDATE()
 if failed then error('job descriptor attach failed') end
 local ok=pcall(function()
  local t,paused=guard()
  if phase=='new' then
   assert(paused);phase='attaching'
   app=assert(X4LAN_AUTHORITY_JOB_REGISTRY_HOST.new_x4({enabled=true,epoch=epoch,baseline={},expose_actor=true,
    attach_saved_registry=true,exclusive_registry_consumer=true,expected_last=10054,
    expected_save_path=cfg.authority_load_save_path,capacity=128,window=cfg.authority_job_window,
    timeout=10,probe=assert(X4LAN_AUTHORITY_JOB_REGISTRY_PROBE),report=report,done=done,fault=fail}))
   assert(app:start())
  elseif phase=='attaching' then
   assert(paused);local alive,state=app:tick();assert(alive)
   if state=='attached_wait_running' then
    log('READY registry_epoch='..epoch..' run_epoch='..run..' baseline=10054');phase='resume_request'
   end
  elseif phase=='resume_request' then
   assert(paused and app:state()=='attached_wait_running');Unpause();phase='resume_wait'
  elseif phase=='resume_wait' then
   if not paused then log('RESUMED run_epoch='..run);phase='running' end
  elseif phase=='running' then
   assert(not paused);local alive,state=app:tick();assert(alive or state=='done')
  elseif phase=='descriptor' then
   -- Do not pump the host while one descriptor is pending. Its already
   -- registered asynchronous fault handler remains active; overflow fences.
   assert(not paused and app:state()=='waiting' and descriptor and descriptor:tick())
  elseif phase=='pause_request' then
   assert(not paused);Pause();phase='pause_wait'
  elseif phase=='pause_wait' then
   if paused then settled=t;phase='pause_settle' end
  elseif phase=='pause_settle' then
   assert(paused)
   if t-settled>=0.1 then log('PAUSED run_epoch='..run);phase='done' end
  else assert(phase=='done' and paused) end
 end)
 if not ok then fail();error('job descriptor attach failed') end
 return phase=='done'
end
