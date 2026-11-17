local module = dofile('tools/dev/authority_player_registry_enroll.lua')
local registry = dofile('src/authority/lua/ship_registry_client.lua')
local epoch, nonce = string.rep('a', 32), string.rep('b', 32)

local function setup(guard)
 local calls = {}
 local owner = assert(module.new({enabled=true, epoch=epoch, nonce=nonce, timeout=30,
  clock=function() return 1 end, guard=guard or function() return true end,
  issue=function(screen, operation, arguments)
   calls[#calls+1] = {screen=screen, operation=operation, arguments=arguments}
   return true
  end,
  parse=function(value) return tonumber(value) end,
  key=function(value) return tostring(value) end,
  valid=function(actor, sector) return actor ~= nil and sector ~= nil end,
  to_md_actor=function(actor) return actor end,
  registry=registry}))
 return owner, calls
end

local function accepted(value) assert(value == true) end
local function start(owner)
 accepted(owner:start())
 accepted(owner:registry_event('Epoch', epoch))
 accepted(owner:registry_event('Count', 2))
 accepted(owner:tick())
end
local function read(owner, slot, actor, sector)
 return owner:fixture_event(nonce..'|'..epoch..'|'..slot..'|'..actor..'|'..sector)
end
local function finish_one(owner, index, actor)
 accepted(owner:registry_event('Enrolled', index))
 accepted(owner:tick())
 accepted(owner:registry_event('Actor', actor))
 accepted(owner:tick())
 accepted(owner:registry_event('Enrolled', index))
 accepted(owner:tick())
end

do
 local owner, calls = setup()
 start(owner)
 accepted(read(owner, 1, '0x11', '0xa'))
 finish_one(owner, 3, 17)
 accepted(read(owner, 2, '0x12', '0xb'))
 finish_one(owner, 4, 18)
 accepted(owner:registry_event('Epoch', epoch))
 accepted(owner:registry_event('Count', 4))
 accepted(owner:tick())
 assert(owner:state() == 'done')
 local value = owner:take_result()
 assert(value.count == 4 and value.indices[1] == 3 and value.indices[2] == 4)
 assert(owner:state() == 'completed')
 local operations = {}
 for _, call in ipairs(calls) do operations[#operations+1] = call.operation end
 assert(table.concat(operations, ',') == 'Status,Read,Enroll,Resolve,Enroll,Read,Enroll,Resolve,Enroll,Status')
 assert(not table.concat(operations, ','):match('Initialize'))
end

do
 local owner = setup()
 assert(owner:take_result() == nil and owner:state() == 'failed')
end

do
 local owner
 owner = setup(function() return not owner or owner:state() ~= 'done' end)
 start(owner)
 accepted(read(owner, 1, '0x11', '0xa')); finish_one(owner, 3, 17)
 accepted(read(owner, 2, '0x12', '0xb')); finish_one(owner, 4, 18)
 accepted(owner:registry_event('Epoch', epoch)); accepted(owner:registry_event('Count', 4))
 assert(not owner:tick() and owner:state() == 'failed')
 assert(owner:take_result() == nil)
end

do
 local owner = setup()
 start(owner)
 accepted(read(owner, 1, '0x11', '0xa'))
 accepted(owner:registry_event('Enrolled', 2))
 assert(not owner:tick() and owner:state() == 'failed')
end

do
 local owner = setup()
 start(owner)
 accepted(read(owner, 1, '0x11', '0xa'))
 finish_one(owner, 3, 17)
 assert(not read(owner, 2, '0x11', '0xb') and owner:state() == 'failed')
end

do
 local owner = setup()
 start(owner)
 assert(not owner:fixture_event(nonce..'|'..epoch..'|2|0x11|0xa') and owner:state() == 'failed')
end
