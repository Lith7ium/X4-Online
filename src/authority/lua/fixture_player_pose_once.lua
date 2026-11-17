-- Opt-in one-shot orchestration only. This module has no X4 bindings or hook.
-- The caller must prove frame equivalence and supply locally resolved actors;
-- a successful callback here is not itself proof of that equivalence.
local M = {}

local function token(value)
 return type(value) == 'string' and #value == 32 and value:match('^[0-9a-f]+$') ~= nil
end

local function finite(value, limit)
 return type(value) == 'number' and value == value and math.abs(value) <= limit
end

local function positive_integer(value)
 return finite(value, 9007199254740991) and value >= 1 and value % 1 == 0
end

local function sector_name(value)
 return type(value) == 'string' and #value >= 1 and #value <= 128 and value:match('^[A-Za-z0-9_]+$') ~= nil
end

local function copy_grant(value)
 if type(value) ~= 'table' or getmetatable(value) ~= nil then return nil end
 local grant = {index=value.index, epoch=value.epoch, generation=value.generation,
  source=value.source, sequence=value.sequence, sector=value.sector, frame=value.frame}
 if (grant.index ~= 3 and grant.index ~= 4) or not positive_integer(grant.sequence) or
  not token(grant.epoch) or not token(grant.generation) or not token(grant.source) or
  not token(grant.frame) or not sector_name(grant.sector) or
  grant.epoch == grant.generation or grant.epoch == grant.source or grant.epoch == grant.frame or
  grant.generation == grant.source or grant.generation == grant.frame or grant.source == grant.frame then
  return nil
 end
 return grant
end

local function copy_pose(value)
 if type(value) ~= 'table' or getmetatable(value) ~= nil then return nil end
 local pose = {x=value.x, y=value.y, z=value.z, yaw=value.yaw, pitch=value.pitch, roll=value.roll}
 for _, axis in ipairs({'x', 'y', 'z'}) do if not finite(pose[axis], 10000000) then return nil end end
 for _, axis in ipairs({'yaw', 'pitch', 'roll'}) do if not finite(pose[axis], 2 * math.pi) then return nil end end
 return pose
end

local function same_grant(left, right)
 if not left or not right then return false end
 for _, name in ipairs({'index', 'epoch', 'generation', 'source', 'sequence', 'sector', 'frame'}) do
  if left[name] ~= right[name] then return false end
 end
 return true
end

local function same_pose(left, right)
 if not left or not right then return false end
 for _, name in ipairs({'x', 'y', 'z', 'yaw', 'pitch', 'roll'}) do
  if left[name] ~= right[name] then return false end
 end
 return true
end

local function local_identity(value, grant)
 if type(value) ~= 'table' or getmetatable(value) ~= nil or value.registry_verified ~= true or value.registry_index ~= grant.index or
  value.registry_epoch ~= grant.epoch or value.valid ~= true or value.operational ~= true or value.is_ship ~= true or
  value.player_context_verified ~= true or value.docked ~= false or value.stored ~= false or
  value.sector_name ~= grant.sector or value.actor == nil or value.actor == false or value.actor == 0 or
  value.sector == nil or value.sector == false or value.sector == 0 or
  value.parent == nil or value.parent == false or value.parent == 0 or
  value.controlled == nil or value.occupied == nil or value.container_ship == nil or
  value.actor == value.controlled or value.actor == value.occupied or value.actor == value.container_ship then
  return nil
 end
 return {actor=value.actor, sector=value.sector, parent=value.parent, sector_name=value.sector_name,
  controlled=value.controlled, occupied=value.occupied, container_ship=value.container_ship}
end

local function same_identity(left, right)
 if not left or not right then return false end
 for _, name in ipairs({'actor', 'sector', 'parent', 'sector_name', 'controlled', 'occupied', 'container_ship'}) do
  if left[name] ~= right[name] then return false end
 end
 return true
end

function M.new(options)
 if type(options) ~= 'table' or getmetatable(options) ~= nil or options.enabled ~= true then return nil, 'disabled' end
 local grant = copy_grant(options.grant)
 if not grant then return nil, 'invalid_grant' end
 for _, name in ipairs({'guard', 'inspect', 'frame_attested', 'write'}) do
  if type(options[name]) ~= 'function' then return nil, 'missing_callback' end
 end
 local guard, inspect, frame_attested, write = options.guard, options.inspect, options.frame_attested, options.write
 local state, busy, write_entered = 'ready', false, false
 local api = {}

 local function guarded_identity()
  if guard() ~= true then return nil end
  local identity = local_identity(inspect(grant.index), grant)
  if not identity then return nil end
  -- The callback must attest this exact source, frame and locally resolved
  -- sector/parent. Identical names or copied save references are insufficient.
  local request = {index=grant.index, epoch=grant.epoch, generation=grant.generation,
   source=grant.source, sequence=grant.sequence, sector=grant.sector, frame=grant.frame,
   local_sector=identity.sector, local_parent=identity.parent}
  if frame_attested(request) ~= true or not same_grant(grant, copy_grant(request)) or
   request.local_sector ~= identity.sector or request.local_parent ~= identity.parent or guard() ~= true then
   return nil
  end
  return identity
 end

 function api:apply(sample)
  if busy or state ~= 'ready' then state = 'failed'; return false, 'unavailable' end
  busy = true
  state = 'checking' -- a rejected attempt is never silently retried
  local ok, result = pcall(function()
   local sample_grant = copy_grant(sample)
   local target = sample_grant and copy_pose(sample.pose) or nil
   if not target or not same_grant(grant, sample_grant) then return 'rejected' end
   local first = guarded_identity()
   if not first then return 'rejected' end
   local second = guarded_identity()
   if not same_identity(first, second) or state ~= 'checking' then return 'rejected' end
   -- No callback is made between the last identity check and this write.
   local intended = copy_pose(target)
   write_entered = true
   if write(second.actor, second.sector, target) ~= true then return 'uncertain' end
   local after = guarded_identity()
   if state ~= 'checking' or not same_pose(target, intended) or not same_identity(second, after) then return 'uncertain' end
   return 'written'
  end)
  busy = false
  if not ok then result = write_entered and 'uncertain' or 'rejected' end
  state = result == 'written' and 'done' or 'failed'
  return result == 'written', result
 end

 function api:state() return state end
 return api
end

return M
