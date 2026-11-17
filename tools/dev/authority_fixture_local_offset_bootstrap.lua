-- Loaded only in the disposable, explicitly opted-in recovery profile.
local cfg = X4LAN_CONFIG
if not cfg or cfg.authority_local_offset_enabled ~= true then return end
assert(type(X4LAN_FIXTURE_LOCAL_OFFSET) == 'table')
local owner, reported_failure
function X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
 if reported_failure then return end
 if not owner then
  owner = assert(X4LAN_FIXTURE_LOCAL_OFFSET.new({
   enabled=true, epoch=cfg.authority_local_offset_epoch, nonce=cfg.authority_local_offset_nonce,
   slot=cfg.authority_local_offset_slot, timeout=cfg.authority_local_offset_timeout,
   expected_save_path=cfg.authority_load_save_path,
   guard=function()
    return type(X4LAN_AUTHORITY_MARKER_READY) == 'function' and X4LAN_AUTHORITY_MARKER_READY() == true
   end,
   log=function(line) DebugError('[X4LAN] AUTH_FIXTURE_LOCAL_OFFSET ' .. line); return true end,
  }))
 end
 local ok = owner:tick()
 if not ok then
  reported_failure = true
  DebugError('[X4LAN] AUTH_FIXTURE_LOCAL_OFFSET ERROR')
 end
end
