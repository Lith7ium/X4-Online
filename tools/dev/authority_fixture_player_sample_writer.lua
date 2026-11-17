-- One disposable XYZ-only fixture sample write. The source-to-server frame
-- is an explicit experiment assumption, not a same-run or Windows proof.
-- Only locally resolved X4 handles are used; the caller owns the UDP lease.
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
 assert(token(options.epoch) and token(options.nonce) and token(options.generation)
  and token(options.lease) and token(options.attempt))
 local distinct = {}
 for _, value in ipairs({options.epoch, options.nonce, options.generation, options.lease, options.attempt}) do
  assert(not distinct[value]); distinct[value] = true
 end
 assert(options.slot == 1 or options.slot == 2)
 assert(type(options.expected_save_path) == 'string' and options.expected_save_path:sub(1, 1) == '/'
  and options.expected_save_path:sub(-11) == '/45841/save')
 assert(type(options.guard) == 'function' and type(options.log) == 'function')
 assert((type(options.net) == 'table' or type(options.net) == 'userdata') and
  type(options.net.send) == 'function' and type(options.net.receive) == 'function' and
  type(options.net.pending) == 'function')
 assert(finite(options.timeout, 120) and options.timeout > 0)
 assert(type(X4LAN_RESOLVE_STRING) == 'table' and type(X4LAN_RESOLVE_STRING.parse_hex) == 'function'
  and type(X4LAN_RESOLVE_STRING.actor_u64) == 'function')
 -- A caller cannot retarget a pending request by changing its options table.
 options = {epoch=options.epoch, nonce=options.nonce, slot=options.slot, generation=options.generation,
  lease=options.lease, attempt=options.attempt, net=options.net, expected_save_path=options.expected_save_path,
  timeout=options.timeout, guard=options.guard, log=options.log}
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
 local state, busy, write_entered = 'waiting', false, false
 local paused_since_ready = false
 local last_time, deadline, local_identity, observation, command = nil, nil, nil, nil, nil
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
  assert(player_valid() and not paused() and type(X4LAN_AUTHORITY_MARKER_READY) == 'function'
   and X4LAN_AUTHORITY_MARKER_READY() == true)
  local now = GetCurRealTime()
  assert(finite(now, 1e15) and now >= 0 and (not last_time or now >= last_time)
   and (not deadline or now < deadline))
  last_time = now
  assert(options.guard() == true and state ~= 'failed' and player_valid() and not paused())
  local after_guard = GetCurRealTime()
  assert(finite(after_guard, 1e15) and after_guard >= now and state ~= 'failed'
   and (not deadline or after_guard < deadline))
  last_time = after_guard
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
   local distance = math.sqrt((command.x-before.x)^2 + (command.y-before.y)^2 + (command.z-before.z)^2)
   -- This is only a distance bound, not collision-clearance evidence.
   assert(finite(distance, 100000000) and distance >= 1 and distance <= 50)
   local target = {x=command.x, y=command.y, z=command.z,
    yaw=before.yaw * 180 / math.pi, pitch=before.pitch * 180 / math.pi, roll=before.roll * 180 / math.pi}
   inspect(identity)
   assert(options.log('WRITE_ENTERED ' .. options.nonce) == true)
   inspect(identity)
   -- The MD response is asynchronous: reject any command queued while waiting.
   assert(options.net:pending() == false)
   check() -- the readiness call itself may have consumed the remaining deadline
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
   assert(distance <= 0.5 and options.net:pending() == false)
   local reply = table.concat({'R', options.lease, options.attempt, 'RESULT', command.request,
    options.epoch, options.generation, tostring(index), command.sequence, expected_sector, command.digest,
    string.format('%.17g', observation.before.x), string.format('%.17g', observation.before.y),
    string.format('%.17g', observation.before.z), string.format('%.17g', after.x),
    string.format('%.17g', after.y), string.format('%.17g', after.z)}, '|')
   assert(options.log('OBSERVED ' .. options.nonce .. ' ' .. command.digest) == true)
   check()
   state = 'done' -- no second command may be accepted after this point
   assert(options.net:send(reply) == true)
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
 local function parse_command(packet)
  assert(type(packet) == 'string' and #packet <= 768)
  local fields = {}; for field in (packet .. '|'):gmatch('(.-)|') do fields[#fields+1] = field end
  assert(#fields == 14 and fields[1] == 'P' and fields[2] == options.lease and fields[3] == options.attempt
   and fields[4] == 'WRITE' and token(fields[5]) and fields[6] == options.epoch
   and fields[7] == options.generation and fields[8] == tostring(index) and fields[10] == expected_sector
   and fields[11]:match('^[0-9a-f]+$') and #fields[11] == 64)
  assert(fields[9]:match('^[1-9]%d*$') and #fields[9] <= 16)
  local sequence = tonumber(fields[9])
  assert(sequence and sequence <= 9007199254740991 and string.format('%.0f', sequence) == fields[9])
  local coordinates = {}
  for position=12,14 do
   assert(#fields[position] <= 32 and fields[position]:match('^[%d%.%+%-eE]+$'))
   coordinates[position] = tonumber(fields[position])
   assert(finite(coordinates[position], 10000000))
  end
  return {request=fields[5], sequence=fields[9], digest=fields[11],
   x=coordinates[12], y=coordinates[13], z=coordinates[14]}
 end
 function api:tick()
  if busy or state == 'failed' then return fail() end
  if state == 'done' then return true, 'observed' end
  busy = true
  local ok = pcall(function()
   if state == 'waiting' then
    -- A normal join may pause the server before either source is ready.
    if paused() then return end
    check()
    assert(options.net:send(table.concat({'R', options.lease, options.attempt, 'READY', options.epoch,
     options.generation, tostring(index), expected_sector}, '|')) == true)
    check(); state = 'ready'
   elseif state == 'ready' then
    if paused() then
     paused_since_ready = true
     assert(options.net:pending() == false)
     return
    end
    if paused_since_ready then
     assert(options.net:pending() == false)
     paused_since_ready = false
    end
    check()
    local waiting = options.net:pending(); assert(type(waiting) == 'boolean')
    if not waiting then return end
    command = parse_command(options.net:receive())
    assert(options.net:pending() == false)
    deadline = last_time + options.timeout; issue(1)
   else
    check(); assert(options.net:pending() == false)
    if state == 'post_pending' then issue(2)
    else assert(state == 'pre' or state == 'post') end
   end
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
