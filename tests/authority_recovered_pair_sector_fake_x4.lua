-- Real recovered client, motion/sector owners and UDP; X4 ABI and MD are fake.
-- The caller owns process cleanup and must not treat this as native X4 evidence.
local ffi = require('ffi')
ffi.cdef[[int usleep(unsigned int);]]
local netlib = assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')), 'luaopen_x4lan_net'))()
local port = assert(tonumber(os.getenv('TEST_NET_PORT')))
local log = assert(io.open(assert(os.getenv('TEST_CLIENT_LOG')), 'a'))
log:write('[TEST] synthetic client started\n'); log:flush()
local handlers, pending = {}, {}
local buffered, sector_reads, stopped = 0, 0, false

function RegisterEvent(name, callback)
 assert(not handlers[name]); handlers[name] = callback; return true
end
function GetCurRealTime() return netlib.monotonic() end
function AddUITriggeredEvent(screen, operation, args)
 if screen == 'X4AuthoritySavedBaselineMotionBind' then
  assert(operation == 'Bind' and args.baseline == 10054 and args.index == 42)
  pending[#pending + 1] = {kind='binding', args=args}
 elseif screen == 'X4AuthorityPlayerSectorInterest' then
  assert(operation == 'Read' and buffered == 1 and sector_reads == 0)
  sector_reads = sector_reads + 1
  pending[#pending + 1] = {kind='sector', args=args}
 else
  error('unexpected MD screen')
 end
 return true
end
function ConvertStringToLuaID(value) return ffi.new('uint64_t', tonumber(value)) end
function ConvertIDTo64Bit(value) return value end
function GetComponentData(ref, field, ...)
 if ref == 43 and field == 'macro' then return 'sector_a' end
 assert(ref == 41); return false, false, false
end
function DebugError(value)
 assert(type(value) == 'string' and not value:find('\n', 1, true))
 log:write('[=ERROR=] '..value..'\n'); log:flush()
end
function X4LAN_RECOVERED_CLIENT_LOAD_READY() return true end

-- Load the same real UDP Lua module while keeping the native library private.
local original_loadlib = package.loadlib
package.loadlib = function() return function() return netlib end end
X4LAN_LOCAL_UDP_MODULE = dofile('src/authority/lua/local_udp_module.lua')
X4LAN_RESOLVE_STRING = dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_REPLICA_MOTION_BINDING = dofile('src/authority/lua/replica_motion_binding.lua')
X4LAN_SAVED_BASELINE_MOTION_BINDING = dofile('src/authority/lua/saved_baseline_motion_binding.lua')
X4LAN_MOTION_BUFFER = dofile('src/authority/lua/motion_buffer.lua')
local real_buffer = X4LAN_MOTION_BUFFER.new
X4LAN_MOTION_BUFFER.new = function(options)
 local track = real_buffer(options)
 local push = track.push
 function track:push(sample, arrival)
  assert(buffered == 0 and sample.frame == 'sector_a' and sample.sequence == 2 and sample.source_time == 1.5)
  assert(sample.pose[1] == 2 and sample.pose[2] == 2 and sample.pose[3] == 3)
  assert(sample.rate and sample.rate[1] == 2 and sample.rate[2] == 0 and sample.rate[3] == 0)
  local accepted = push(self, sample, arrival)
  assert(accepted == true)
  buffered = buffered + 1
  io.stdout:write('CLIENT_BUFFERED\n'); io.stdout:flush()
  return accepted
 end
 return track
end
X4LAN_CLIENT_MOTION_EVENT_ROUTER = dofile('src/authority/lua/client_motion_event_router.lua')
X4LAN_MOTION_CLIENT_OWNER = dofile('src/authority/lua/motion_client_owner.lua')
X4LAN_PLAYER_SECTOR_INTEREST = dofile('src/authority/lua/player_sector_interest.lua')
local recovered = dofile('tools/dev/authority_recovered_client_motion.lua')
local epoch = ('c'):rep(32)
local owner = assert(recovered.new_x4({
 enabled=true, port=port, lease=('a'):rep(32), attempt=('b'):rep(32), epoch=epoch,
 generation=('d'):rep(32), nonce=('e'):rep(32), router_generation=('1'):rep(32),
 baseline=10054, index=42, timeout=5, expected_save_path='/private/45841/save',
 player_sector={incarnation=('2'):rep(32), nonce=('3'):rep(32), after_bound=true},
}))
package.loadlib = original_loadlib

while true do
 assert(owner:tick(), 'client owner fault')
 while #pending > 0 do
  local event = table.remove(pending, 1)
  if event.kind == 'binding' then
   handlers['X4AuthoritySavedBaselineMotionBind.Result'](nil,
    event.args.request_id..'|Bound|42|0x29|0x2b')
  else
   assert(event.kind == 'sector')
   handlers['X4AuthorityPlayerSectorInterest.Result'](nil,
    event.args.request_id..'|'..event.args.epoch..'|'..event.args.incarnation..'|ok|0x2b|sector_a')
  end
 end
 if owner:state() == 'stopped' and not stopped then
  assert(buffered == 1 and sector_reads == 1 and #pending == 0)
  stopped = true
  io.stdout:write('CLIENT_STOPPED\n'); io.stdout:flush()
 end
 -- Keep the stopped owner alive for delayed UDP/MD fault checks.
 ffi.C.usleep(1000)
end
