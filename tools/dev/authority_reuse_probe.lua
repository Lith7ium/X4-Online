-- Disposable, opt-in, single-process same-slot three-save experiment only.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_reuse_probe~=true then return end
local ffi=require('ffi');local C=ffi.C
ffi.cdef[[bool IsPlayerValid(void);bool IsSaveListLoadingComplete(void);void ReloadSaveList(void);bool IsFullscreenCutsceneActive(void);]]
local stage='waiting';local failed=false;local state,net,next_hello,loaded_at,binding,paused_at_save
local cycle=1
local slot='save_009'
local function log(text) DebugError('[X4LAN] AUTH_REUSE '..text) end
local function fail(reason)
 if not failed then failed=true;stage='failed';log('ERROR code='..reason) end
end
local function report(row)
 if row.status=='failed' then fail('state_'..row.reason);return end
 if row.operation=='pause' and row.status=='confirmed' and stage=='pausing' then
  stage='paused';log('PAUSE '..cycle..' confirmed')
 elseif row.operation=='save' and row.status=='native_event_only' and stage=='saving' then
  assert(binding.is_paused(),'pause lost at save receipt')
  assert(row.slot==slot and row.request_id==3*cycle-1 and row.title=='X4 Authority '..cfg.authority_cycle_id..' '..row.request_id,'save receipt mismatch')
  paused_at_save=binding.game_time()
  stage='await_verification';log('SAVE '..cycle..' native_event_only')
 elseif row.operation=='resume' and row.status=='confirmed' and stage=='resuming' then
  log('RESUME '..cycle..' confirmed')
  if cycle==3 then stage='done';log('COMPLETE')
  else stage='await_progress' end
 else fail('unexpected_receipt') end
end
local function submit(op,params)
 local opnum=op=='pause' and 1 or op=='save' and 2 or 3
 local ok,reason=state:submit('isolated-supervisor',cfg.authority_cycle_id,(cycle-1)*3+opnum,op,params)
 if not ok then fail('submit_'..reason) end
end
local function initialize()
 assert(cfg.test_profile=='45841' and type(cfg.authority_control_lease)=='string' and
  #cfg.authority_control_lease==32 and cfg.authority_control_lease:match('^[0-9a-f]+$'))
 assert(type(cfg.authority_cycle_id)=='string' and #cfg.authority_cycle_id==32 and cfg.authority_cycle_id:match('^[0-9a-f]+$'))
 assert(type(cfg.authority_control_port)=='number' and cfg.authority_control_port>=1 and cfg.authority_control_port<=65535)
 binding=assert(X4LAN_AUTHORITY_X4_CONTROL_ENGINE).new({enabled=true,test_profile='45841'})
 assert(type(SaveGame)=='function')
 binding.save=function(slot,name) SaveGame(slot,name) end
 state=assert(X4LAN_AUTHORITY_CONTROL_STATE).new({enabled=true,owner='isolated-supervisor',
  world_epoch=cfg.authority_cycle_id,enable_verified_reuse=true,timeout_seconds=120,pause_settle_seconds=.1},binding,report)
 assert(X4LAN_AUTHORITY_X4_CONTROL_ENGINE.register_save_event({enabled=true},state,RegisterEvent))
 local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
 net=lib.open('127.0.0.1',cfg.authority_control_port)
 C.ReloadSaveList();stage='save_list';log('ARMED')
end
local function frame()
 if failed or stage=='done' then return end
 if not C.IsPlayerValid() then return end
 local now=GetCurRealTime()
 if stage=='waiting' then
  loaded_at=loaded_at or now
  if now-loaded_at<3 then return end
  initialize()
 end
 if stage=='await_verification' and (not binding.is_paused() or binding.game_time()~=paused_at_save) then
  fail('verification_pause_lost');return
 end
 if now>=(next_hello or 0) then
  assert(net:send('HELLO|'..cfg.authority_control_lease)==true,'hello failed')
  next_hello=now+.25
 end
 for _=1,16 do
  local packet=net:receive();if not packet then break end
  if packet=='VERIFIED|'..cfg.authority_control_lease..'|'..cycle and stage=='await_verification' then
   local ok,reason=state:confirm_save('isolated-supervisor',cfg.authority_cycle_id,3*cycle-1,true)
   if not ok then fail('verify_'..reason);return end
   stage='resuming';submit('resume')
  end
 end
 if stage=='save_list' then
  if not C.IsSaveListLoadingComplete() then return end
  local entries=GetSaveList({save_009=true})
  assert(type(entries)=='table','save list unavailable')
  for _,entry in pairs(entries) do
   assert(entry.filename~='save_009','owned slot not empty')
  end
  if C.IsFullscreenCutsceneActive() or not binding.saving_possible() then return end
  stage='pausing';submit('pause')
 elseif stage=='await_progress' then
  if binding.is_paused() then fail('unexpected_pause');return end
  if binding.game_time()<paused_at_save+2 then return end
  if C.IsFullscreenCutsceneActive() or not binding.saving_possible() then return end
  cycle=cycle+1;stage='pausing';submit('pause')
 elseif stage=='paused' then
  stage='saving'
  local params={slot=slot,exclusive_owner=true}
  if cycle==1 then params.empty_owned_slot=true else params.overwrite_verified_owned_slot=true end
  submit('save',params)
 end
 if failed or stage=='done' then return end
 local ok,reason=state:on_update()
 if not ok then fail('update_'..reason) end
end
SetScript('onUpdate',function()
 local ok=pcall(frame)
 if not ok then fail('probe') end
end)
