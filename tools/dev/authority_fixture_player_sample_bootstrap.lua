-- Private opt-in server fixture only. Driven by the existing bridge onUpdate.
local cfg = X4LAN_CONFIG
if not cfg or cfg.authority_fixture_sample_write ~= true then return end
local ffi = require('ffi')
local owner, faulted
function X4LAN_FIXTURE_SAMPLE_WRITE_TICK()
 if faulted then return false end
 if not owner then
  assert(ffi.os == 'Linux', 'fixture server diagnostic requires Linux')
  local load = assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so', 'luaopen_x4lan_net'))
  local net = assert(load().open('127.0.0.1', cfg.fixture_sample_write_port))
  owner = assert(X4LAN_FIXTURE_PLAYER_SAMPLE_WRITER.new({
   enabled=true, epoch=cfg.fixture_sample_write_epoch, generation=cfg.fixture_sample_write_generation,
   nonce=cfg.fixture_sample_write_nonce, lease=cfg.fixture_sample_write_lease,
   attempt=cfg.fixture_sample_write_attempt, slot=cfg.fixture_sample_write_slot,
   expected_save_path=cfg.authority_load_save_path, timeout=cfg.fixture_sample_write_timeout, net=net,
   guard=function()
    return type(X4LAN_AUTHORITY_MARKER_READY) == 'function' and X4LAN_AUTHORITY_MARKER_READY() == true
   end,
   log=function(line) DebugError('[X4LAN] AUTH_FIXTURE_SAMPLE_WRITE ' .. line); return true end,
  }))
 end
 local ok = owner:tick()
 if not ok then
  faulted = true
  DebugError('[X4LAN] AUTH_FIXTURE_SAMPLE_WRITE ERROR')
 end
 return ok
end
