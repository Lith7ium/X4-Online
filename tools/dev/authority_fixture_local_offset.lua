-- One disposable, local X4 offset probe. No network input or frame claim.
-- The caller must install the MD cue, call tick from the existing X4 update
-- owner, and provide a guard for its private process/profile/checkpoint.
local M = {}
local constructed = false

local function token(value)
 return type(value) == 'string' and #value == 32 and value:match('^[0-9a-f]+$') ~= nil
end
local function finite(value, limit)
 return type(value) == 'number' and value == value and math.abs(value) <= limit
end

function M.new(options)
 if type(options) ~= 'table' or options.enabled ~= true then return nil, 'disabled' end
 if constructed then return nil, 'already_constructed' end
 assert(token(options.epoch) and token(options.nonce) and options.epoch ~= options.nonce)
 assert(options.slot == 1 or options.slot == 2)
 assert(type(options.expected_save_path) == 'string' and options.expected_save_path:sub(1, 1) == '/'
  and options.expected_save_path:sub(-11) == '/45841/save')
 assert(type(options.guard) == 'function' and type(options.log) == 'function')
 assert(finite(options.timeout, 120) and options.timeout > 0)
 assert(type(X4LAN_RESOLVE_STRING) == 'table' and type(X4LAN_RESOLVE_STRING.parse_hex) == 'function'
  and type(X4LAN_RESOLVE_STRING.actor_u64) == 'function')
 -- A caller cannot retarget a pending request by changing its options table.
 options = {epoch=options.epoch, nonce=options.nonce, slot=options.slot,
  expected_save_path=options.expected_save_path, timeout=options.timeout, guard=options.guard, log=options.log}
 constructed = true -- even initialization errors must not permit a second owner
 local ffi = require('ffi')
 if not pcall(ffi.typeof, 'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof, 'UIPosRot') then ffi.cdef('typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;') end
 ffi.cdef[[
  const char* GetSaveFolderPath(void); bool IsPlayerValid(void); bool IsGamePaused(void);
  bool IsValidComponent(UniverseID); bool IsComponentOperational(UniverseID);
  bool IsComponentClass(UniverseID,const char*); UniverseID GetContextByClass(UniverseID,const char*,bool);
  UniverseID GetPlayerControlledShipID(void); UniverseID GetPlayerOccupiedShipID(void);
  UniverseID GetPlayerContainerID(void); UIPosRot GetObjectPositionInSector(UniverseID);
  void SetObjectSectorPos(UniverseID,UniverseID,UIPosRot);
 ]]
 local C = ffi.C
 -- Resolve the actual X4 exports during construction, before any write.
 local get_path, player_valid, paused = C.GetSaveFolderPath, C.IsPlayerValid, C.IsGamePaused
 local valid, operational, is_class, context = C.IsValidComponent, C.IsComponentOperational, C.IsComponentClass, C.GetContextByClass
 local controlled, occupied, container = C.GetPlayerControlledShipID, C.GetPlayerOccupiedShipID, C.GetPlayerContainerID
 local get_pose, set_pose = C.GetObjectPositionInSector, C.SetObjectSectorPos
 local expected_sector = ({'cluster_33_sector001_macro', 'cluster_45_sector001_macro'})[options.slot]
 local state, busy, write_entered = 'new', false, false
 local last_time, deadline, local_identity, observation = nil, nil, nil, nil
 local index = options.slot + 2
 local api = {}

 local function fail()
  state = 'failed'
  return false, write_entered and 'uncertain' or 'rejected'
 end
 local function check()
  assert(state ~= 'failed' and options.guard() == true)
  local path = get_path()
  assert(path ~= nil and path ~= ffi.NULL and ffi.string(path):gsub('\\', '/'):gsub('/+$', '') == options.expected_save_path)
  assert(player_valid() and paused() and type(X4LAN_AUTHORITY_MARKER_READY) == 'function'
   and X4LAN_AUTHORITY_MARKER_READY() == true)
  local now = GetCurRealTime()
  assert(finite(now, 1e15) and now >= 0 and (not last_time or now >= last_time)
   and (not deadline or now < deadline))
  last_time = now
  assert(options.guard() == true and state ~= 'failed' and player_valid() and paused())
 end
 local function key(value)
  local id = X4LAN_RESOLVE_STRING.actor_u64(value)
  return id and tostring(id):gsub('ULL$', '') or nil
 end
 local function reference(value)
  local expected = assert(key(value))
  assert(expected:match('^[1-9]%d*$'))
  local ref = assert(ConvertStringToLuaID(expected))
  local kind = type(ref)
  if kind == 'number' or kind == 'cdata' then assert(key(ref) == expected) else assert(kind == 'userdata') end
  assert(key(ConvertIDTo64Bit(ref)) == expected)
  return ref
 end
 local function inspect(identity)
  check()
  local actor, sector, parent = identity.actor, identity.sector, identity.parent
  local actor_ref, sector_ref = reference(actor), reference(sector)
  assert(valid(actor) and operational(actor) and is_class(actor, 'ship'))
  assert(valid(sector) and is_class(sector, 'sector') and context(actor, 'sector', false) == sector)
  assert(valid(parent) and is_class(parent, 'zone') and context(actor, 'zone', false) == parent)
  local own, occupied_ship, player_container = controlled(), occupied(), container()
  assert(own ~= actor and occupied_ship ~= actor and player_container ~= actor and player_container ~= 0 and valid(player_container))
  local player_ship = context(player_container, 'ship', true)
  if player_ship ~= 0 then assert(player_ship ~= actor) else assert(context(player_container, 'station', true) ~= 0) end
  local docked, docking, stored = GetComponentData(actor_ref, 'isdocked', 'isdocking', 'isinternallystored')
  assert(docked == false and docking == false and stored == false)
  local macro, owner = GetComponentData(actor_ref, 'macro', 'owner')
  assert(macro == 'ship_arg_s_fighter_01_a_macro' and owner == 'player')
  assert(GetComponentData(sector_ref, 'macro') == expected_sector)
  check()
 end
 local function read_pose(identity)
  inspect(identity)
  local position = get_pose(identity.actor)
  local result = {}
  for _, field in ipairs({'x', 'y', 'z', 'yaw', 'pitch', 'roll'}) do
   result[field] = tonumber(position[field]); assert(finite(result[field], 10000000))
  end
  inspect(identity)
  return result
 end
 local function issue(phase)
  check()
  state = phase == 1 and 'pre' or 'post'
  assert(AddUITriggeredEvent('X4AuthorityFixtureLocalOffset', 'Inspect',
   {request_id=options.nonce .. tostring(phase), epoch=options.epoch, slot=options.slot}) ~= false)
  check()
 end
 local function parse_result(value, phase)
  assert(type(value) == 'string' and #value <= 160)
  local request, epoch, result_index, actor, sector, parent = value:match(
   '^([0-9a-f]+)|([0-9a-f]+)|([0-9]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)$')
  assert(request == options.nonce .. tostring(phase) and epoch == options.epoch and result_index == tostring(index))
  local parsed = {actor=X4LAN_RESOLVE_STRING.parse_hex(actor), sector=X4LAN_RESOLVE_STRING.parse_hex(sector),
   parent=X4LAN_RESOLVE_STRING.parse_hex(parent)}
  assert(parsed.actor and parsed.sector and parsed.parent)
  return parsed
 end
 local function same_identity(left, right)
  return left.actor == right.actor and left.sector == right.sector and left.parent == right.parent
 end
 local function result(value)
  assert(state == 'pre' or state == 'post')
  check()
  local phase = state == 'pre' and 1 or 2
  local identity = parse_result(value, phase)
  if phase == 1 then
   local_identity = identity
   local before = read_pose(identity)
   local second = read_pose(identity)
   for _, field in ipairs({'x', 'y', 'z', 'yaw', 'pitch', 'roll'}) do assert(before[field] == second[field]) end
   local target_x = before.x + 10
   assert(finite(target_x, 10000000) and target_x > before.x)
   local target = {x=target_x, y=before.y, z=before.z,
    yaw=before.yaw * 180 / math.pi, pitch=before.pitch * 180 / math.pi, roll=before.roll * 180 / math.pi}
   inspect(identity)
   assert(options.log('WRITE_ENTERED ' .. options.nonce) == true)
   inspect(identity)
   write_entered = true -- an exception can follow a partial native effect
   set_pose(identity.actor, identity.sector, ffi.new('UIPosRot', target))
   local after = read_pose(identity)
   observation = {before=before, target=target, after=after}
   state = 'post_pending' -- dispatch the second MD read from the next update
  else
   assert(same_identity(identity, local_identity))
   inspect(identity)
   local after = observation.after
   local distance = math.sqrt((after.x - observation.target.x)^2 + (after.y - observation.target.y)^2 + (after.z - observation.target.z)^2)
   assert(finite(distance, 100000000))
   assert(options.log(('OBSERVED %s %d %.17g %.17g %.17g %.17g %.17g %.17g %.17g'):format(
    options.nonce, index, observation.before.x, observation.before.y, observation.before.z, after.x, after.y, after.z, distance)) == true)
   check()
   state = 'done'
  end
 end
 local function receive(value)
  if busy or state == 'failed' or state == 'done' then fail(); return end
  busy = true
  local ok = pcall(result, value)
  busy = false
  if not ok then fail() end
 end
 assert(RegisterEvent('X4AuthorityFixtureLocalOffset.Result', function(_, value) receive(value) end) ~= false)
 assert(RegisterEvent('X4AuthorityFixtureLocalOffset.Refused', function() fail() end) ~= false)
 function api:tick()
  if busy or state == 'failed' then return fail() end
  if state == 'done' then return true, 'observed' end
  busy = true
  local ok = pcall(function()
   check()
   if state == 'new' then deadline = last_time + options.timeout; issue(1)
   elseif state == 'post_pending' then issue(2)
   else assert(state == 'pre' or state == 'post') end
  end)
  busy = false
  if not ok then return fail() end
  return true, state
 end
 function api:state() return state end
 function api:result()
  if state ~= 'done' then return nil end
  return {before={x=observation.before.x,y=observation.before.y,z=observation.before.z},
   after={x=observation.after.x,y=observation.after.y,z=observation.after.z}}
 end
 return api
end
return M
