local ffi = require('ffi')
local fake_library = ffi.load(assert(arg[1]), true)
local module = dofile('tools/dev/authority_player_registry_enroll.lua')
local registry = dofile('src/authority/lua/ship_registry_client.lua')
local resolver = dofile('tools/dev/authority_registry_resolve_string.lua')
local epoch, nonce = string.rep('a', 32), string.rep('b', 32)
GetCurRealTime = function() return 1 end
AddUITriggeredEvent = function() return true end
ConvertStringToLuaID = function(value) return ffi.new('uint64_t', tonumber(value)) end
ConvertIDTo64Bit = function(value) return value end
GetComponentData = function(_, field)
 if field == 'owner' then return 'player' end
 return false, false, false
end
local owner = assert(module.new_x4({enabled=true, epoch=epoch, nonce=nonce, timeout=30,
 expected_save_path='/tmp/45841/save', external_guard=function() return true end,
 registry=registry, resolve=resolver}))
local function event(name, value) assert(owner:registry_event(name, value)) end
local function read(slot, actor, sector)
 assert(owner:fixture_event(nonce..'|'..epoch..'|'..slot..'|'..actor..'|'..sector))
end
local function finish(index, actor)
 event('Enrolled', index); assert(owner:tick())
 event('Actor', ffi.new('uint64_t', actor)); assert(owner:tick())
 event('Enrolled', index); assert(owner:tick())
end
assert(owner:start())
event('Epoch', epoch); event('Count', 2); assert(owner:tick())
read(1, '0xa', '0xb'); finish(3, 10)
read(2, '0xc', '0xd'); finish(4, 12)
event('Epoch', epoch); event('Count', 4); assert(owner:tick())
assert(owner:state() == 'done')
local completed = assert(owner:take_result())
assert(completed.count == 4 and completed.indices[2] == 4)
assert(fake_library ~= nil)
