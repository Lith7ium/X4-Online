-- Disposable diagnostic only. The load probe is the sole onUpdate owner.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_job_attach~=true then return end
local ffi=require('ffi');local C=ffi.C
local epoch,run=cfg.authority_job_registry_epoch,cfg.authority_ticket.world_epoch
assert(type(epoch)=='string' and #epoch==32 and epoch:match('^[0-9a-f]+$'))
assert(type(run)=='string' and #run==32 and run:match('^[0-9a-f]+$') and run~=epoch)
assert(type(Pause)=='function' and type(Unpause)=='function')
local phase='new';local app,failed,start,last,settled=nil,false,nil,nil,nil
local function log(s) DebugError('[X4LAN] AUTH_JOB_ATTACH '..s) end
local function fail() if not failed then failed=true;phase='failed';log('ERROR') end end
local function guard()
 local p=C.GetSaveFolderPath()
 assert(p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_load_save_path)
 assert(C.IsPlayerValid())
 local t=GetCurRealTime();assert(type(t)=='number' and t==t and t>=0 and t<math.huge and (not last or t>=last))
 start=start or t;last=t;assert(t-start<=cfg.authority_job_window+45)
 return t,C.IsGamePaused()
end
local function report(row)
 assert(phase=='running' and row.epoch==epoch and row.birth_confirmed==false and row.delivery_confirmed==false)
 assert(row.classification=='previously_observed' or row.classification=='previously_unobserved_existing_index' or row.classification=='new_registry_entry')
 log(('EVENT sequence=%.0f index=%.0f class=%s'):format(row.sequence,row.index,row.classification));return true
end
local function done(row)
 assert(phase=='running' and row.registry_mode=='attached' and row.baseline_count==10054 and row.baseline_known_count==0)
 assert(row.birth_confirmed==false and row.delivery_confirmed==false and row.coverage=='unknown')
 assert(row.classification=='inconclusive_no_events' or row.classification=='local_activations_observed')
 log(('SUMMARY observed=%.0f acknowledged=%.0f baseline=%.0f class=%s'):format(row.observed,row.acknowledged,row.baseline_count,row.classification))
 phase='pause_request';return true
end
function X4LAN_JOB_ATTACH_UPDATE()
 if failed then error('job attach failed') end
 local ok=pcall(function()
  local t,paused=guard()
  if phase=='new' then
   assert(paused);phase='attaching'
   app=assert(X4LAN_AUTHORITY_JOB_REGISTRY_HOST.new_x4({enabled=true,epoch=epoch,baseline={},
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
  elseif phase=='pause_request' then
   assert(not paused);Pause();phase='pause_wait'
  elseif phase=='pause_wait' then
   if paused then settled=t;phase='pause_settle' end
  elseif phase=='pause_settle' then
   assert(paused)
   if t-settled>=0.1 then log('PAUSED run_epoch='..run);phase='done' end
  else assert(phase=='done' and paused) end
 end)
 if not ok then fail();error('job attach failed') end
 return phase=='done'
end
