-- Opt-in, paused fixture registration using the historical uncorrelated registry.
-- The existing recovery owner must exclusively route events and call tick().
local M = {}

local function token(value)
 return type(value) == 'string' and #value == 32 and value:match('^[0-9a-f]+$') ~= nil
end

function M.new(options)
 if type(options) ~= 'table' or options.enabled ~= true then return nil, 'disabled' end
 assert(token(options.epoch) and token(options.nonce) and options.epoch ~= options.nonce)
 assert(type(options.timeout) == 'number' and options.timeout > 0 and options.timeout <= 120)
 for _, name in ipairs({'clock', 'guard', 'issue', 'parse', 'key', 'valid', 'to_md_actor'}) do
  assert(type(options[name]) == 'function', name .. ' required')
 end
 assert(type(options.registry) == 'table' and type(options.registry.new) == 'function')
 local state, busy, started, last_time = 'new', false, nil, nil
 local client, reply, actor, sector, first_key, first_sector = nil, nil, nil, nil, nil, nil
 local slot, index = 1, nil
 local api = {}

 local function fail(reason)
  state = 'failed'
  if client then client:close() end
  return false, reason
 end

 local function check()
  local now = options.clock()
  assert(type(now) == 'number' and now == now and now >= 0 and now < math.huge)
  assert(not last_time or now >= last_time)
  started = started or now
  assert(now - started < options.timeout and options.guard() == true)
  last_time = now
 end

 local function run(action)
  if busy or state == 'failed' or state == 'closed' then return fail('state') end
  busy = true
  local ok = pcall(function()
   check(); assert(state ~= 'failed')
   action(); assert(state ~= 'failed')
   check(); assert(state ~= 'failed')
  end)
  busy = false
  if not ok then return fail('operation') end
  return true
 end

 local function current_actor()
  return actor ~= nil and sector ~= nil and options.valid(actor, sector) == true
 end

 function api:start()
  return run(function()
   assert(state == 'new')
   client = assert(options.registry.new({enabled=true, epoch=options.epoch, timeout=options.timeout,
    clock=options.clock, issue=options.issue, key=options.key, to_md_actor=options.to_md_actor,
    valid=function(value) return options.valid(value, sector) end,
    complete=function(operation, value)
     if reply ~= nil then return false end
     reply = {operation=operation, value=value}
     return true
    end}))
   state = 'status_wait'
   assert(client:status())
  end)
 end

 function api:tick()
  return run(function()
   assert(state ~= 'new' and state ~= 'done')
   assert(client:tick())
   if not reply then return end
   local current = reply
   reply = nil
   if state == 'status_wait' then
    assert(current.operation == 'Status' and current.value.epoch == options.epoch and current.value.count == 2)
    state = 'read_wait'
    assert(options.issue('X4AuthorityPlayerRegistryRead', 'Read',
     {epoch=options.epoch, request_id=options.nonce, slot=slot}) == true)
   elseif state == 'enroll_wait' then
    assert(current.operation == 'Enroll' and current.value == slot + 2 and current_actor())
    index = current.value
    state = 'resolve_wait'
    assert(client:resolve(index))
   elseif state == 'resolve_wait' then
    assert(current.operation == 'Resolve' and options.key(current.value) == options.key(actor) and current_actor())
    state = 'repeat_wait'
    assert(client:enroll(actor))
   elseif state == 'repeat_wait' then
    assert(current.operation == 'Enroll' and current.value == index and current_actor())
    if slot == 1 then
     first_key, first_sector = options.key(actor), options.key(sector)
     slot, actor, sector, index = 2, nil, nil, nil
     state = 'read_wait'
     assert(options.issue('X4AuthorityPlayerRegistryRead', 'Read',
      {epoch=options.epoch, request_id=options.nonce, slot=slot}) == true)
    else
     assert(options.key(actor) ~= first_key and options.key(sector) ~= first_sector)
     state = 'final_status_wait'
     assert(client:status())
    end
   elseif state == 'final_status_wait' then
    assert(current.operation == 'Status' and current.value.epoch == options.epoch and current.value.count == 4 and current_actor())
    assert(client:close())
    state = 'done'
   else
    error('unexpected registry response')
   end
  end)
 end

 function api:fixture_event(value)
  return run(function()
   assert(state == 'read_wait' and type(value) == 'string' and #value <= 256)
   local request, epoch, received_slot, actor_hex, sector_hex = value:match(
    '^([0-9a-f]+)|([0-9a-f]+)|([12])|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)$')
   assert(request == options.nonce and epoch == options.epoch and received_slot == tostring(slot))
   actor, sector = options.parse(actor_hex), options.parse(sector_hex)
   assert(actor ~= nil and sector ~= nil and type(options.key(actor)) == 'string' and
    type(options.key(sector)) == 'string' and current_actor())
   if slot == 2 then assert(options.key(actor) ~= first_key and options.key(sector) ~= first_sector) end
   state = 'enroll_wait'
   assert(client:enroll(actor))
  end)
 end

 function api:registry_event(name, value)
  return run(function()
   assert(client ~= nil and client:on_event(name, value))
  end)
 end

 function api:refused() return fail('refused') end
 -- A result is available only after the tick that set done has returned and
 -- passed its final guard. The caller must publish it only after this method.
 function api:take_result()
  if busy or state ~= 'done' then fail('result_unavailable'); return nil end
  busy = true
  local ok = pcall(function() check(); assert(state == 'done') end)
  busy = false
  if not ok then fail('result_guard'); return nil end
  state = 'completed'
  return {indices={3,4}, count=4}
 end
 function api:state() return state end
 return api
end

function M.new_x4(config)
 if type(config) ~= 'table' or config.enabled ~= true then return nil, 'disabled' end
 assert(type(config.expected_save_path) == 'string' and type(config.external_guard) == 'function')
 assert(type(config.resolve) == 'table' and type(config.resolve.parse_hex) == 'function'
  and type(config.resolve.actor_u64) == 'function')
 for _, name in ipairs({'GetCurRealTime', 'AddUITriggeredEvent', 'ConvertStringToLuaID',
  'ConvertIDTo64Bit', 'GetComponentData'}) do
  assert(type(_G[name]) == 'function', name .. ' required')
 end
 local ffi = require('ffi')
 if not pcall(ffi.typeof, 'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 ffi.cdef[[bool IsGamePaused(void); bool IsPlayerValid(void); bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID); bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool); UniverseID GetPlayerContainerID(void);
 UniverseID GetPlayerOccupiedShipID(void); UniverseID GetPlayerControlledShipID(void);
 const char* GetSaveFolderPath(void);]]
 local C, resolve = ffi.C, config.resolve
 local function guard()
  local path = C.GetSaveFolderPath()
  return path ~= nil and path ~= ffi.NULL and
   ffi.string(path):gsub('\\', '/'):gsub('/+$', '') == config.expected_save_path and
   C.IsPlayerValid() and C.IsGamePaused() and config.external_guard() == true
 end
 local function exact_actor(value)
  local kind = type(value)
  if kind == 'number' or kind == 'cdata' then return resolve.actor_u64(value) end
  if kind ~= 'userdata' then return nil end
  return resolve.actor_u64(ConvertIDTo64Bit(value))
 end
 local function key(value)
  local actor = exact_actor(value)
  if not actor then return nil end
  return (tostring(actor):gsub('ULL$', ''))
 end
 local function valid(value, sector)
  local actor, area = exact_actor(value), exact_actor(sector)
  if not actor or not area or not guard() then return false end
  if not C.IsValidComponent(actor) or not C.IsComponentOperational(actor) or
    not C.IsComponentClass(actor, 'ship') or not C.IsValidComponent(area) or
    not C.IsComponentClass(area, 'sector') or C.GetContextByClass(actor, 'sector', false) ~= area or
    C.GetPlayerContainerID() == actor or C.GetPlayerOccupiedShipID() == actor or
    C.GetPlayerControlledShipID() == actor then return false end
  local id = ConvertStringToLuaID(key(actor))
  if not id or exact_actor(id) ~= actor then return false end
  local docked, docking, stored = GetComponentData(id, 'isdocked', 'isdocking', 'isinternallystored')
  return docked == false and docking == false and stored == false and
   GetComponentData(id, 'owner') == 'player' and guard() and
   C.IsValidComponent(actor) and C.IsComponentOperational(actor) and
   C.GetContextByClass(actor, 'sector', false) == area
 end
 local options = {}
 for name, value in pairs(config) do options[name] = value end
 options.clock = GetCurRealTime
 options.guard = guard
 options.issue = function(screen, operation, arguments)
  return AddUITriggeredEvent(screen, operation, arguments) ~= false
 end
 options.parse = resolve.parse_hex
 options.key = key
 options.valid = valid
 options.to_md_actor = function(_, actor_key) return ConvertStringToLuaID(actor_key) end
 return M.new(options)
end

X4LAN_PLAYER_REGISTRY_ENROLL = M
return M
