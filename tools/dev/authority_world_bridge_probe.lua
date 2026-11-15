-- Explicit isolated-profile probe. Never included or registered by default.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_world_bridge~=true then return end
local ffi=require('ffi');local C=ffi.C
ffi.cdef[[bool IsPlayerValid(void);bool IsSaveListLoadingComplete(void);void ReloadSaveList(void);]]
local started,bridge,net,engine,next_hello,loaded_at=false,nil,nil,nil,0,nil
local function frame()
 if not C.IsPlayerValid() then return end
 local now=GetCurRealTime()
 if not loaded_at then loaded_at=now;return end
 if not started and now-loaded_at>=3 then
  assert(cfg.test_profile=='45841')
  engine=assert(X4LAN_AUTHORITY_X4_CONTROL_ENGINE.new({enabled=true,test_profile='45841'}))
  local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
  net=lib.open('127.0.0.1',cfg.authority_control_port)
  C.ReloadSaveList();started=true
 end
 if not started then return end
 if not bridge then
  if not C.IsSaveListLoadingComplete() then return end
  local entries=GetSaveList({save_009=true});assert(type(entries)=='table')
  for _,entry in pairs(entries) do assert(entry.filename~='save_009','owned slot not empty') end
  bridge=assert(X4LAN_AUTHORITY_LOCAL_CONTROL_BRIDGE.new({enabled=true,empty_owned_slot=true,
   lease=cfg.authority_control_lease,world_epoch=cfg.authority_world_epoch,
   marker_required=cfg.authority_marker_required,
   store_marker=function(marker)
    AddUITriggeredEvent('X4AuthorityCheckpointMarker','Store',{marker=marker})
   end},engine,net))
  if cfg.authority_marker_required then
   RegisterEvent('X4AuthorityCheckpointMarker.Stored',function(_,marker)
    local ok,reason=bridge:marker_stored(marker);assert(ok,reason)
   end)
  end
  assert(X4LAN_AUTHORITY_X4_CONTROL_ENGINE.register_save_event({enabled=true},bridge.state,RegisterEvent))
 end
 if now>=next_hello then
  assert(net:send('HELLO|'..cfg.authority_control_lease..'|'..cfg.authority_world_epoch)==true)
  next_hello=now+.25
 end
 local ok,reason=bridge:update();assert(ok,reason)
end
local stopped=false
SetScript('onUpdate',function()
 if stopped then return end
 local ok,err=pcall(frame)
 if not ok then stopped=true;DebugError('[X4LAN] AUTH_WORLD_BRIDGE ERROR '..tostring(err)) end
end)
