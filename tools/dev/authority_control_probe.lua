-- Explicitly enabled disposable, single-process test. No multiplayer protocol.
-- The external supervisor alone may approve resume after validating the file.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_control_probe~=true then return end
local ffi=require('ffi');local C=ffi.C
ffi.cdef[[bool IsPlayerValid(void);bool IsSaveListLoadingComplete(void);void ReloadSaveList(void);bool IsFullscreenCutsceneActive(void);]]
local stage='waiting';local failed=false;local state,net,next_hello,loaded_at,binding,paused_at_save
local function log(text) DebugError('[X4LAN] AUTH_CONTROL '..text) end
local function fail(reason)
 if not failed then failed=true;stage='failed';log('ERROR code='..reason) end
end
local function report(row)
 if row.status=='failed' then fail('state_'..row.reason);return end
 if row.operation=='pause' and row.status=='confirmed' and stage=='pausing' then
  stage='paused';log('PAUSE confirmed')
 elseif row.operation=='save' and row.status=='native_event_only' and stage=='saving' then
  assert(binding.is_paused(),'pause lost at save receipt')
  paused_at_save=binding.game_time()
  stage='await_verification';log('SAVE native_event_only')
 elseif row.operation=='resume' and row.status=='confirmed' and stage=='resuming' then
  stage='done';log('RESUME confirmed');log('COMPLETE')
 else fail('unexpected_receipt') end
end
local function submit(id,op,params)
 local ok,reason=state:submit('isolated-supervisor','isolated-epoch',id,op,params)
 if not ok then fail('submit_'..reason) end
end
local function initialize()
 assert(cfg.test_profile=='45841' and type(cfg.authority_control_lease)=='string' and
  #cfg.authority_control_lease==32 and cfg.authority_control_lease:match('^[0-9a-f]+$'))
 assert(type(cfg.authority_control_port)=='number' and cfg.authority_control_port>=1 and cfg.authority_control_port<=65535)
 binding=assert(X4LAN_AUTHORITY_X4_CONTROL_ENGINE).new({enabled=true,test_profile='45841'})
 state=assert(X4LAN_AUTHORITY_CONTROL_STATE).new({enabled=true,owner='isolated-supervisor',
  world_epoch='isolated-epoch',timeout_seconds=120,pause_settle_seconds=.1},binding,report)
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
  if packet=='VERIFIED|'..cfg.authority_control_lease and stage=='await_verification' then
   stage='resuming';submit(3,'resume')
  end
 end
 if stage=='save_list' then
  if not C.IsSaveListLoadingComplete() then return end
  local entries=GetSaveList({save_009=true})
  assert(type(entries)=='table','save list unavailable')
  for _,entry in pairs(entries) do
   assert(entry.filename~='save_009','owned slot not empty')
  end
  -- Save eligibility may change when X4 pauses; this is only the preflight.
  -- The control state checks it again after pause has been confirmed.
  if C.IsFullscreenCutsceneActive() or not binding.saving_possible() then return end
  stage='pausing';submit(1,'pause')
 elseif stage=='paused' then
  stage='saving';submit(2,'save',{slot='save_009',exclusive_owner=true,empty_owned_slot=true})
 end
 if failed or stage=='done' then return end
 local ok,reason=state:on_update()
 if not ok then fail('update_'..reason) end
end
SetScript('onUpdate',function()
 local ok=pcall(frame)
 if not ok then fail('probe') end
end)
