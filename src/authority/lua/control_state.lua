-- Inert unless new() is explicitly enabled. No X4 calls or registrations.
-- A single caller must serialize all calls and own every save operation.
local M={}
local MAX=9007199254740991
local function finite(n) return type(n)=='number' and n==n and n~=math.huge and n~=-math.huge end
local function token(s) return type(s)=='string' and #s>0 and #s<=128 and s:match('^[A-Za-z0-9_.%-]+$')~=nil end
function M.new(config,engine,report)
 if type(config)~='table' or config.enabled~=true then return nil,'disabled' end
 assert(token(config.owner) and token(config.world_epoch), 'owner and epoch required')
 local expected_owner, expected_epoch=config.owner,config.world_epoch
 assert(type(engine)=='table' and type(report)=='function', 'engine and report required')
 for _,name in ipairs({'ready','is_paused','game_time','real_time','pause','resume','saving_possible','save'}) do
  assert(type(engine[name])=='function', 'missing engine function')
 end
 local timeout=config.timeout_seconds or 30
 local settle=config.pause_settle_seconds or .1
 assert(finite(timeout) and timeout>0 and timeout<=600 and finite(settle) and settle>0 and settle<=5,
  'invalid control timing')
 local pending,last_id,last_time=nil,0,nil
 local failed,paused_confirmed,paused_time,save_used=false,false,nil,false
 local reporting=false
 local state={}
 local function invoke(name,...)
  local ok,value=pcall(engine[name],...)
  return ok,value
 end
 local function finish(status,reason)
  local request=pending;pending=nil
  if status=='failed' then failed=true;paused_confirmed=false;paused_time=nil end
  if request then
   reporting=true
   local ok=pcall(report,{world_epoch=expected_epoch,request_id=request.id,operation=request.op,status=status,reason=reason})
   reporting=false
   if not ok then failed=true;paused_confirmed=false;paused_time=nil end
  end
  return not failed
 end
 local function now()
  local ok,t=invoke('real_time')
  if not ok or not finite(t) or t<0 or (last_time and t<last_time) then return nil end
  last_time=t;return t
 end
 local function current()
  local ok_ready,ready=invoke('ready')
  local ok_paused,paused=invoke('is_paused')
  local ok_time,time=invoke('game_time')
  if not ok_ready or ready~=true or not ok_paused or type(paused)~='boolean' or not ok_time or not finite(time) or time<0 then return nil end
  return {paused=paused,time=time}
 end
 function state:submit(owner,epoch,id,op,params)
  if reporting then return false,'reentrant_report' end
  if owner~=expected_owner or epoch~=expected_epoch then return false,'owner_or_epoch' end
  if failed then return false,'faulted' end
  if pending then return false,'busy' end
  if type(id)~='number' or id%1~=0 or id<1 or id>MAX or id<=last_id then return false,'stale_request' end
  if op~='pause' and op~='resume' and op~='save' then return false,'operation' end
  if op~='save' and params~=nil then return false,'parameters' end
  if op=='save' and (type(params)~='table' or params.exclusive_owner~=true or params.empty_owned_slot~=true or
     type(params.slot)~='string' or not params.slot:match('^save_%d%d%d$')) then return false,'save_contract' end
  if op=='save' and save_used then return false,'one_save_per_process' end
  local t=now();local observation=current()
  if failed then return false,'faulted' end
  if not t or not observation then failed=true;return false,'engine_unavailable' end
  if op=='save' then
   if not paused_confirmed or not observation.paused or observation.time~=paused_time then
    failed=true;paused_confirmed=false;return false,'pause_not_confirmed'
   end
   local ok,possible=invoke('saving_possible')
   if failed then return false,'faulted' end
   if not ok or possible~=true then failed=true;paused_confirmed=false;return false,'saving_unavailable' end
  end
  last_id=id
  pending={id=id,op=op,deadline=t+timeout,start_time=observation.time}
  if op=='pause' then
   paused_confirmed=false;paused_time=nil
   if not observation.paused then
    local ok=invoke('pause')
    if not ok then finish('failed','pause_call');return false,'pause_call' end
    if failed then return false,'foreign_save_event' end
   end
  elseif op=='resume' then
   paused_confirmed=false;paused_time=nil
   if observation.paused then
    local ok=invoke('resume')
    if not ok then finish('failed','resume_call');return false,'resume_call' end
    if failed then return false,'foreign_save_event' end
   end
  else
   save_used=true -- even a failed or uncertain call must never be retried
   pending.slot=params.slot
   local ok=invoke('save',params.slot)
   if not ok then finish('failed','save_call');return false,'save_call' end
   if failed then return false,'save_event_failure' end
  end
  return true,'pending'
 end
 function state:on_game_saved(success)
  if reporting then return false,'reentrant_report' end
  if failed then return false,'faulted' end
  if not pending or pending.op~='save' then
   -- An unrelated native save breaks the exclusive-owner premise.
   failed=true;paused_confirmed=false;paused_time=nil
   if pending then finish('failed','foreign_save_event') end
   return false,'foreign_save_event'
  end
  if pending.event~=nil then finish('failed','duplicate_save_event');return false,'duplicate_save_event' end
  if success~=true and success~=1 then finish('failed','save_event_failure');return false,'save_event_failure' end
  pending.event=true
  return true,'event_recorded'
 end
 function state:on_update()
  if reporting then return false,'reentrant_report' end
  if failed then return false,'faulted' end
  if not pending then return true,'idle' end
  local active=pending
  local t=now();local observation=current()
  if failed or pending~=active then return false,'faulted' end
  if not t or not observation then finish('failed','engine_unavailable');return false,'engine_unavailable' end
  if t>pending.deadline then finish('failed','timeout');return false,'timeout' end
  if observation.time<pending.start_time then finish('failed','game_time_regressed');return false,'game_time_regressed' end
  if pending.op=='pause' then
   if observation.paused then
    if not pending.settled_at or observation.time~=pending.settled_time then
     pending.settled_at,pending.settled_time=t,observation.time
    elseif t-pending.settled_at>=settle then
     paused_confirmed=true;paused_time=observation.time
     if not finish('confirmed','pause_observed') then return false,'report_failed' end
     return true,'confirmed'
    end
   else pending.settled_at,pending.settled_time=nil,nil end
  elseif pending.op=='resume' then
   if not observation.paused and observation.time>pending.start_time then
    if not finish('confirmed','resume_observed') then return false,'report_failed' end
    return true,'confirmed'
   end
  else
   if not observation.paused or observation.time~=paused_time then
    finish('failed','save_pause_lost');return false,'save_pause_lost'
   end
   if pending.event then
    -- The supervisor must independently verify/commit the resulting file.
    if not finish('native_event_only','file_verification_required') then return false,'report_failed' end
    return true,'native_event_only'
   end
  end
  return true,'pending'
 end
 return state
end
-- X4 UI loaders execute files for side effects and ignore their return value.
X4LAN_AUTHORITY_CONTROL_STATE=M
return M
