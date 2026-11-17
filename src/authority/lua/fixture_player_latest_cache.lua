-- Offline, default-off local sample cache. No X4 hook, network or game writes.
-- The caller owns the sampler, its single event route and pause barrier.
local M = {}
local MAX_INTEGER = 9007199254740991

local function plain(value) return type(value) == 'table' and getmetatable(value) == nil end
local function token(value)
 return type(value) == 'string' and #value == 32 and value:match('^[0-9a-f]+$') ~= nil
end
local function finite(value, maximum)
 return type(value) == 'number' and value == value and math.abs(value) <= maximum
end
local function integer(value)
 return finite(value, MAX_INTEGER) and value >= 1 and value % 1 == 0
end
local function name(value)
 return type(value) == 'string' and #value > 0 and #value <= 128 and value:match('^[A-Za-z0-9_]+$') ~= nil
end
local function copy(value)
 if type(value) ~= 'table' then return value end
 assert(plain(value))
 local result = {}; for key, item in pairs(value) do result[key] = copy(item) end; return result
end
local function equal(left, right)
 if type(left) ~= type(right) then return false end
 if type(left) ~= 'table' then return left == right end
 if not plain(left) or not plain(right) then return false end
 for key, value in pairs(left) do if right[key] == nil or not equal(value, right[key]) then return false end end
 for key in pairs(right) do if left[key] == nil then return false end end
 return true
end
local function valid_vector(value, axes, maximum)
 if not plain(value) then return false end
 for _, axis in ipairs(axes) do if not finite(value[axis], maximum) then return false end end
 local count = 0; for _ in pairs(value) do count = count + 1 end
 return count == #axes
end
local function valid_grant(grant)
 if not plain(grant) then return false end
 local fields = {index=true, epoch=true, generation=true, source=true, frame=true, sector=true}
 for key in pairs(grant) do if not fields[key] then return false end end
 return (grant.index == 3 or grant.index == 4) and token(grant.epoch) and
  token(grant.generation) and token(grant.source) and token(grant.frame) and name(grant.sector) and
  grant.epoch ~= grant.generation and grant.epoch ~= grant.source and grant.epoch ~= grant.frame and
  grant.generation ~= grant.source and grant.generation ~= grant.frame and grant.source ~= grant.frame
end
local function valid_sample(sample, grant)
 if not plain(sample) or sample.version ~= 2 or sample.epoch ~= grant.epoch or
  sample.generation ~= grant.generation or sample.index ~= grant.index or sample.sector_macro ~= grant.sector or
  not integer(sample.sequence) or not finite(sample.source_time, 1e12) or sample.source_time < 0 or
  not finite(sample.x, 1e7) or not finite(sample.y, 1e7) or not finite(sample.z, 1e7) or
  not valid_vector(sample.orientation, {'yaw', 'pitch', 'roll'}, 2 * math.pi) then return false end
 if (sample.velocity == nil) ~= (sample.angular_rate == nil) then return false end
 if sample.velocity ~= nil and (not valid_vector(sample.velocity, {'x', 'y', 'z'}, 5000) or
  not valid_vector(sample.angular_rate, {'yaw', 'pitch', 'roll'}, 2 * math.pi)) then return false end
 local fields = {version=true,epoch=true,generation=true,index=true,sector_macro=true,sequence=true,
  source_time=true,x=true,y=true,z=true,orientation=true,velocity=true,angular_rate=true}
 for key in pairs(sample) do if not fields[key] then return false end end
 return true
end

function M.new(options)
 if not plain(options) or options.enabled ~= true then return nil, 'disabled' end
 if not valid_grant(options.grant) or not finite(options.max_age, 60) or options.max_age <= 0 then
  return nil, 'invalid_context'
 end
 for _, callback in ipairs({'clock', 'guard', 'authority', 'inspect', 'validate_capture', 'quiescent', 'reset_sampler'}) do
  if type(options[callback]) ~= 'function' then return nil, 'missing_callback' end
 end
 local grant = copy(options.grant)
 local clock, guard, authority, inspect = options.clock, options.guard, options.authority, options.inspect
 local validate_capture, quiescent, reset_sampler = options.validate_capture, options.quiescent, options.reset_sampler
 local max_age = options.max_age
 local state, busy, cached, last_clock = 'running', false, nil, nil
 local actor, last_capture, last_delivery, last_time = nil, 0, 0, nil
 local need_capture_baseline, need_delivery_baseline = true, true
 local api = {}

 local function fail(reason)
  state = 'failed'; cached = nil; busy = false
  return false, reason
 end
 local function checked_context()
  local observed_time = clock()
  if not finite(observed_time, 1e12) or observed_time < 0 or (last_clock and observed_time < last_clock) then return nil end
  last_clock = observed_time
  if guard() ~= true then return nil end
  local grant_copy = copy(grant)
  if authority(grant_copy) ~= true or not equal(grant_copy, grant) then return nil end
  local value = inspect(grant.index)
  if not plain(value) or value.valid ~= true or value.controlled ~= true or
   value.sector ~= grant.sector or value.frame ~= grant.frame or
   value.actor == nil or value.actor == false or value.actor == 0 then return nil end
  local pinned = {actor=value.actor, sector=value.sector, frame=value.frame}
  if actor ~= nil and actor ~= pinned.actor then return nil end
  if guard() ~= true or state ~= 'running' then return nil end
  local final_grant = copy(grant)
  if authority(final_grant) ~= true or not equal(final_grant, grant) or state ~= 'running' then return nil end
  local final_time = clock()
  if not finite(final_time, 1e12) or final_time < observed_time or state ~= 'running' or
   not plain(value) or value.valid ~= true or value.controlled ~= true or value.actor ~= pinned.actor or
   value.sector ~= pinned.sector or value.frame ~= pinned.frame then return nil end
  last_clock = final_time
  if actor == nil then actor = pinned.actor end
  return pinned, final_time
 end
 local function same_context(left, right)
  return left and right and left.actor == right.actor and left.sector == right.sector and left.frame == right.frame
 end
 local function enter(required)
  if busy or state ~= required then return false end
  busy = true; return true
 end

 function api:capture(sample)
  if not enter('running') then return fail('unavailable') end
  local ok, result = pcall(function()
   local first = checked_context();assert(first)
   assert(valid_sample(sample, grant) and sample.sequence == last_capture + 1 and
    (not last_time or sample.source_time > last_time) and (not need_capture_baseline or sample.velocity == nil))
   local frozen = copy(sample);local candidate = copy(frozen)
   -- The caller attests that this exact completed sample came from the owned
   -- sampler, which alone computes rates from adjacent local observations.
   assert(validate_capture(candidate) == true and equal(candidate, frozen) and equal(sample, frozen))
   local second, observed_time = checked_context()
   assert(same_context(first, second) and state == 'running' and equal(sample, frozen))
   actor = first.actor;last_capture = frozen.sequence;last_time = frozen.source_time
   need_capture_baseline = false;cached = {sample=frozen, at=observed_time}
   return true
  end)
  if not ok or result ~= true or state ~= 'running' then return fail('capture_failed') end
  busy = false;return true
 end

 function api:pull()
  if not enter('running') then return fail('unavailable') end
  local ok, envelope, status = pcall(function()
   local first = checked_context();assert(first)
   local selected = cached and copy(cached) or nil
   local second, now = checked_context();assert(same_context(first, second) and state == 'running')
   if not selected or now - selected.at > max_age then cached = nil;return nil, 'empty' end
   assert(now >= selected.at and last_delivery < MAX_INTEGER and equal(cached, selected))
   local sample = copy(selected.sample)
   local capture_sequence = sample.sequence
   sample.sequence = last_delivery + 1
   if need_delivery_baseline then sample.velocity = nil;sample.angular_rate = nil end
   -- The output sequence advances only after the final context check.
   local third, final_time = checked_context()
   assert(same_context(first, third) and state == 'running' and equal(cached, selected))
   if final_time - selected.at > max_age then cached = nil;return nil, 'empty' end
   last_delivery = sample.sequence;need_delivery_baseline = false;cached = nil
   return {capture_sequence=capture_sequence, delivery_sequence=last_delivery, sample=sample}, 'sample'
  end)
  if not ok or state ~= 'running' then return fail('pull_failed') end
  busy = false;return envelope, status
 end

 function api:pause()
  if not enter('running') then return fail('unavailable') end
  local ok = pcall(function()
   local first = checked_context();assert(first)
   -- The surrounding protocol must first stop scheduling, drain any pending
   -- MD event and IPC request, and only then attest quiescence.
   assert(quiescent() == true)
   local drained = checked_context();assert(same_context(first, drained) and state == 'running')
   assert(reset_sampler() == true)
   local second = checked_context();assert(same_context(first, second) and state == 'running')
   cached = nil;need_capture_baseline = true;need_delivery_baseline = true;state = 'paused'
  end)
  if not ok or state ~= 'paused' then return fail('pause_failed') end
  busy = false;return true
 end

 function api:resume()
  if not enter('paused') then return fail('unavailable') end
  -- The caller invokes this only after X4 resumed under the same grant.
  state = 'running'
  local ok = pcall(function()
   local first = checked_context();local second = checked_context()
   assert(same_context(first, second) and state == 'running' and cached == nil)
  end)
  if not ok or state ~= 'running' then return fail('resume_failed') end
  busy = false;return true
 end

 function api:state() return state end
 return api
end

X4LAN_FIXTURE_PLAYER_LATEST_CACHE = M
return M
