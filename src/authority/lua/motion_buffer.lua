-- Read-only motion reconstruction for a single explicitly identified fixture.
-- Adapted from the X4LAN_MOTION LAN-lab motion buffer.
-- No game API calls, object lookup, velocity writes or networking.
local M = {}
local MAX_SEQUENCE = 9007199254740991
local PI = math.pi

local function finite(value)
 return type(value) == 'number' and value == value and value ~= math.huge and value ~= -math.huge
end

local function frame(value)
 return type(value) == 'string' and #value > 0 and #value <= 128 and
  value:match('^[A-Za-z0-9_.%-]+$') ~= nil
end

local function angle(radians)
 return (radians + PI) % (2 * PI) - PI
end

local function vector(values, is_rate, dimensions)
 if type(values) ~= 'table' or #values ~= dimensions then return false end
 for index = 1, dimensions do
  local limit = index <= 3 and (is_rate and 100000 or 50000000) or 2 * PI
  if not finite(values[index]) or math.abs(values[index]) > limit then return false end
 end
 return true
end

local function copy(values)
 if not values then return nil end
 local result = {}
 for index = 1, #values do result[index] = values[index] end
 return result
end

local function speed(rate)
 if not rate then return 0 end
 return math.sqrt(rate[1]^2 + rate[2]^2 + rate[3]^2)
end

local function timestamp(seconds)
 return finite(seconds) and seconds >= 0 and seconds <= 1e12
end

local function valid_sample(sample, dimensions)
 return type(sample) == 'table' and frame(sample.frame) and type(sample.sequence) == 'number' and
  sample.sequence % 1 == 0 and sample.sequence >= 1 and sample.sequence <= MAX_SEQUENCE and
  timestamp(sample.source_time) and vector(sample.pose, false, dimensions) and
  (sample.rate == nil or vector(sample.rate, true, dimensions))
end

-- A wrapped-Euler derivative is useful for extrapolation, but is not an engine
-- native angular-velocity vector. Samples must have matching frames, increasing
-- sequence numbers and a positive source-time interval within max_gap. Missing
-- arguments are rejected; sequence numbers need not be consecutive.
function M.estimate(previous, sample, max_gap)
 local dimensions = type(sample) == 'table' and type(sample.pose) == 'table' and #sample.pose or 0
 if (dimensions ~= 3 and dimensions ~= 6) or not valid_sample(previous, dimensions) or
    not valid_sample(sample, dimensions) or previous.frame ~= sample.frame or
    not finite(max_gap) or max_gap <= 0 or max_gap > 60 then return nil end
 local source_seconds = sample.source_time - previous.source_time
 if source_seconds <= .001 or source_seconds > max_gap or sample.sequence <= previous.sequence then return nil end
 local rate = {}
 for index = 1, dimensions do
  local delta = sample.pose[index] - previous.pose[index]
  rate[index] = (index > 3 and angle(delta) or delta) / source_seconds
 end
 if not vector(rate, true, dimensions) then return nil end
 return rate
end

function M.new(options)
 options = options or {}
 assert(type(options) == 'table', 'options must be a table')
 local known = {delay=true, horizon=true, stale=true, teleport_distance=true,
  clock_leak=true, slew=true, dimensions=true, hold_only=true, deferred_arrival=true}
 for key in pairs(options) do assert(known[key], 'unknown motion option') end
 local cfg = {delay=options.delay or .15, horizon=options.horizon or .35,
  stale=options.stale or .75, teleport_distance=options.teleport_distance or 10000,
  clock_leak=options.clock_leak or .002, slew=options.slew or .1}
 local dimensions = options.dimensions or 6
 assert(dimensions == 3 or dimensions == 6, 'invalid motion dimensions')
 assert(options.hold_only == nil or type(options.hold_only) == 'boolean', 'invalid hold mode')
 local hold_only = options.hold_only == true
 assert(options.deferred_arrival == nil or type(options.deferred_arrival) == 'boolean', 'invalid deferred arrival mode')
 local deferred_arrival = options.deferred_arrival == true
 for key, value in pairs(cfg) do
  assert(finite(value) and value >= 0, 'invalid motion option: '..key)
 end
 assert(cfg.delay <= 60 and cfg.horizon <= 60 and cfg.stale > 0 and cfg.stale <= 60 and
  cfg.teleport_distance <= 50000000 and cfg.clock_leak <= 1 and cfg.slew <= 1, 'motion option out of bounds')

 local samples, offset, last_arrival, last_sequence, last_source = {}, nil, nil, 0, nil
 local lag, lag_at, last_render = nil, nil, nil
 local track = {}

 -- source_time is supplied by the source; arrival and now share the observer's clock.
 function track:push(sample, arrival)
  if not valid_sample(sample, dimensions) or not timestamp(arrival) then return false, 'invalid' end
  if sample.sequence <= last_sequence or (last_source and sample.source_time <= last_source) or
     (last_arrival and arrival < last_arrival) or
     (not deferred_arrival and last_render and arrival < last_render) then return false, 'stale' end
  local last = samples[#samples]
  local reason = 'append'
  if last and sample.frame ~= last.frame then
   reason = 'frame'
  elseif last and sample.source_time - last.source_time > cfg.stale then
   reason = 'gap'
  elseif last then
   local distance_squared = 0
   for index = 1, 3 do distance_squared = distance_squared + (sample.pose[index] - last.pose[index])^2 end
   local distance = math.sqrt(distance_squared)
   local allowed_distance = cfg.teleport_distance + speed(last.rate) * (sample.source_time - last.source_time)
   if distance > allowed_distance then reason = 'teleport' end
  end
  if reason ~= 'append' then
   -- A new continuous motion segment needs a new source-to-observer clock
   -- estimate as well as new samples. Keeping the old minimum offset after a
   -- long interruption can put every new sample beyond the prediction horizon.
   samples = {}
   offset, lag, lag_at = nil, nil, nil
  end
  if not hold_only then
   if offset and last_arrival and arrival > last_arrival then
    offset = offset + cfg.clock_leak * (arrival - last_arrival)
   end
   offset = math.min(offset or math.huge, arrival - sample.source_time)
  end
  local rate = copy(sample.rate)
  if reason ~= 'append' then rate = nil end
  samples[#samples + 1] = {frame=sample.frame, sequence=sample.sequence, source_time=sample.source_time,
                           pose=copy(sample.pose), rate=rate}
  while #samples > 16 do table.remove(samples, 1) end
  last_arrival, last_sequence, last_source = arrival, sample.sequence, sample.source_time
  return true, reason
 end

 function track:render(now)
  if not timestamp(now) or (last_render and now < last_render) or
     (last_arrival and now < last_arrival) then return nil, 'invalid-clock' end
  if #samples == 0 then return nil, 'empty' end
  last_render = now
  if hold_only then
   local last = samples[#samples]
   return {frame=last.frame, source_sequence=last.sequence, pose=copy(last.pose), phase='held-clock-unverified'}
  end

  local wanted_lag = offset + cfg.delay
  -- d(source render time)/d(observer time). A snap or repeated clock value
  -- has no established derivative. A moving lag changes the displayed rate.
  local clock_factor
  if not lag or not lag_at or math.abs(wanted_lag - lag) > 1 then
   lag = wanted_lag
  else
   local elapsed = now - lag_at
   local old_lag = lag
   local step = cfg.slew * elapsed
   lag = wanted_lag > lag and math.min(wanted_lag, lag + step) or math.max(wanted_lag, lag - step)
   if elapsed > 0 then
    -- At a reached target, lag is locally constant on the forward side.
    if lag == wanted_lag then clock_factor = 1
    elseif wanted_lag > old_lag then clock_factor = 1 - cfg.slew
    else clock_factor = 1 + cfg.slew end
   end
  end
  lag_at = now
  local target_source_time = now - lag
  local first, last = samples[1], samples[#samples]
  local result = {frame=last.frame, source_sequence=last.sequence, pose={}, phase='held'}
  if target_source_time <= first.source_time then
   result.pose = copy(first.pose)
   result.source_sequence = first.sequence
   return result
  end

  for index = 2, #samples do
   local earlier, later = samples[index - 1], samples[index]
   if target_source_time <= later.source_time then
    local fraction = (target_source_time - earlier.source_time) / (later.source_time - earlier.source_time)
    for dimension = 1, dimensions do
     local delta = later.pose[dimension] - earlier.pose[dimension]
     result.pose[dimension] = dimension > 3 and angle(earlier.pose[dimension] + angle(delta) * fraction) or
      earlier.pose[dimension] + delta * fraction
    end
    result.phase = 'interpolated'
    result.source_sequence = later.sequence
    -- At a knot, adjacent segments may have different slopes. Never infer a
    -- native angular vector from wrapped Euler-coordinate rates.
    if clock_factor and target_source_time ~= later.source_time then
     local velocity, valid = {}, true
     for dimension = 1, 3 do
      velocity[dimension] = (later.pose[dimension] - earlier.pose[dimension]) /
       (later.source_time - earlier.source_time) * clock_factor
      if not finite(velocity[dimension]) or math.abs(velocity[dimension]) > 100000 then valid = false end
     end
     if valid then result.linear_velocity = velocity end
    end
    return result
   end
  end

  local prediction_seconds = math.min(cfg.horizon, math.max(0, target_source_time - last.source_time))
  if last.rate then
   for dimension = 1, dimensions do
    local value = last.pose[dimension] + last.rate[dimension] * prediction_seconds
    result.pose[dimension] = dimension > 3 and angle(value) or value
   end
   if not vector(result.pose, false, dimensions) then return nil, 'out-of-bounds' end
   result.phase = target_source_time - last.source_time < cfg.horizon and 'extrapolated' or 'frozen'
   if result.phase == 'frozen' and clock_factor then
    result.linear_velocity = {0, 0, 0}
   elseif clock_factor then
    local velocity, valid = {}, true
    for dimension = 1, 3 do
     velocity[dimension] = last.rate[dimension] * clock_factor
     if not finite(velocity[dimension]) or math.abs(velocity[dimension]) > 100000 then valid = false end
    end
    if valid then result.linear_velocity = velocity end
   end
  else
   result.pose = copy(last.pose)
   result.phase = 'held-no-rate'
  end
  return result
 end
 return track
end
return M
