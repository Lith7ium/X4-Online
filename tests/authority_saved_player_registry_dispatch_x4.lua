-- Synthetic X4 ABI with the real registry owner, client and dispatcher.
local ffi = require('ffi')
local fake_library = ffi.load(assert(arg[1]), true)
local callbacks, requests, logs, seat_ticks = {}, {}, {}, 0
local epoch, nonce = string.rep('a',32), string.rep('b',32)
X4LAN_CONFIG = {authority_saved_player_registry=true, authority_fixture_epoch=epoch,
 authority_registry_enroll_nonce=nonce, authority_fixture_timeout=60,
 authority_load_save_path='/tmp/45841/save'}
X4LAN_SHIP_REGISTRY_CLIENT = dofile('src/authority/lua/ship_registry_client.lua')
X4LAN_RESOLVE_STRING = dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_PLAYER_REGISTRY_ENROLL = dofile('tools/dev/authority_player_registry_enroll.lua')
GetCurRealTime = function() return 1 end
ConvertStringToLuaID = function(value) return ffi.new('uint64_t', tonumber(value)) end
ConvertIDTo64Bit = function(value) return value end
GetComponentData = function(_, field)
 if field == 'owner' then return 'player' end
 return false, false, false
end
AddUITriggeredEvent = function(screen, operation, arguments)
 requests[#requests+1] = {screen=screen, operation=operation, arguments=arguments}
 return true
end
RegisterEvent = function(name, callback) assert(not callbacks[name]);callbacks[name]=callback end
DebugError = function(value) logs[#logs+1]=value end
X4LAN_AUTHORITY_RECOVERY_SEAT_TICK = function() seat_ticks=seat_ticks+1 end
dofile('tools/dev/authority_saved_player_registry_dispatch.lua')

local function registry_event(name, value)
 assert(callbacks['X4AuthorityShipRegistry.'..name])
 callbacks['X4AuthorityShipRegistry.'..name](nil, value)
end
local function read(slot, actor, sector)
 callbacks['X4AuthorityPlayerRegistryRead.Result'](nil,
  nonce..'|'..epoch..'|'..slot..'|'..actor..'|'..sector)
end
local function finish(index, actor)
 registry_event('Enrolled', index);X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
 registry_event('Actor', ffi.new('uint64_t', actor));X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
 registry_event('Enrolled', index);X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
end

X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
assert(seat_ticks == 0 and requests[1].operation == 'Status')
registry_event('Epoch', epoch);registry_event('Count', 2);X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
read(1,'0xa','0xb');finish(3,10)
read(2,'0xc','0xd');finish(4,12)
assert(seat_ticks == 0)
registry_event('Epoch', epoch);registry_event('Count', 4);X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
assert(seat_ticks == 1 and logs[1] == '[X4LAN] AUTH_PLAYER_REGISTRY ENROLLED 3 4')
local operations = {}
for _, request in ipairs(requests) do operations[#operations+1] = request.operation end
assert(table.concat(operations, ',') == 'Status,Read,Enroll,Resolve,Enroll,Read,Enroll,Resolve,Enroll,Status')
registry_event('Enrolled', 4)
assert(not pcall(X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK) and seat_ticks == 1)
assert(fake_library ~= nil)
