-- Experimental local-only read pair. No registration, transport or X4 writes.
-- The caller owns a fresh, exclusive source sampler and the shared MD router.
local M = {}

local function finite(value)
 return type(value) == 'number' and value == value and value ~= math.huge and value ~= -math.huge
end

function M.new(config)
 if type(config) ~= 'table' or config.enabled ~= true then return nil, 'disabled' end
 assert(type(config.clock) == 'function' and type(config.guard) == 'function' and
        type(config.fault) == 'function' and type(config.sampler) == 'table')
 assert(finite(config.timeout) and config.timeout > 0 and config.timeout <= 120)
 assert(type(config.epoch) == 'string' and #config.epoch == 32 and config.epoch:match('^[0-9a-f]+$'))
 assert(type(config.generation) == 'string' and #config.generation == 32 and
        config.generation:match('^[0-9a-f]+$') and config.generation ~= config.epoch)
 assert(type(config.index) == 'number' and config.index % 1 == 0 and config.index >= 1)
 assert(config.actor ~= nil)
 assert(config.delivery == nil or type(config.delivery) == 'boolean')
 local delivery = config.delivery == true
 local sampler, clock, guard, fault = config.sampler, config.clock, config.guard, config.fault
 local epoch, generation, index, actor, timeout = config.epoch, config.generation, config.index, config.actor, config.timeout
 for _, name in ipairs({'register', 'tick', 'event', 'state', 'expected_request', 'close'}) do
  assert(type(sampler[name]) == 'function', 'sampler method missing')
 end
 local sampler_register, sampler_tick, sampler_event = sampler.register, sampler.tick, sampler.event
 local sampler_request, sampler_close = sampler.expected_request, sampler.close
 local state, busy, previous_clock, deadline = 'new', false, nil, nil
 local first, result, delivery_sample, requests = nil, nil, nil, 0
 local api = {}

 local function fail(reason)
  if state ~= 'failed' then state = 'failed'; pcall(fault, reason) end
  return false
 end
 local function check()
  local prior = state
  if prior == 'failed' or prior == 'stopped' then return false end
  local ok, before = pcall(clock)
  if not ok or state ~= prior or not finite(before) or before < 0 or
     (previous_clock and before < previous_clock) or (deadline and before >= deadline) then return false end
  previous_clock = before
  local allowed, valid = pcall(guard)
  if not allowed or valid ~= true or state ~= prior then return false end
  local again, after = pcall(clock)
  if not again or state ~= prior or not finite(after) or after < before or
     (deadline and after >= deadline) then return false end
  previous_clock = after
  return true
 end
 local function enter()
  if busy or state == 'failed' or state == 'stopped' then return fail('owner_state') end
  busy = true
  if not check() then busy = false; return fail('guard') end
  return true
 end
 local function leave()
  if not check() then busy = false; return fail('guard') end
  busy = false
  return true
 end
 local function request_id()
  local prior = state
  local ok, request = pcall(sampler_request, sampler)
  if not ok or state ~= prior or (request ~= nil and type(request) ~= 'string') then
   fail('sampler_request')
   return nil, false
  end
  return request, true
 end
 local function plain_sample(value, sequence)
  if type(value) ~= 'table' or getmetatable(value) ~= nil or value.version ~= 1 or
     value.epoch ~= epoch or value.generation ~= generation or value.index ~= index or value.sequence ~= sequence or
     type(value.sector_macro) ~= 'string' or not value.sector_macro:match('^[A-Za-z0-9_]+$') or
     #value.sector_macro > 128 or not finite(value.source_time) or value.source_time < 0 then return false end
  for _, axis in ipairs({'x', 'y', 'z'}) do
   if not finite(value[axis]) or math.abs(value[axis]) > 1e7 then return false end
  end
  return true
 end
 local function point(value)
  return {source_time=value.source_time, x=value.x, y=value.y, z=value.z, sector_macro=value.sector_macro}
 end
 local function build_result(a, b)
  local dt = b.source_time - a.source_time
  if a.sector_macro ~= b.sector_macro or dt < 0.02 or dt > 1 or b.velocity == nil then
   return {status='unavailable', reason='frame_interval_or_rate'}
  end
  if type(b.velocity) ~= 'table' or getmetatable(b.velocity) ~= nil then return nil end
  local rate = {}
  for _, axis in ipairs({'x', 'y', 'z'}) do
   local expected = (b[axis] - a[axis]) / dt
   local observed = b.velocity[axis]
   if not finite(expected) or not finite(observed) or math.abs(expected) > 5000 or
      math.abs(observed - expected) > 1e-9 * math.max(1, math.abs(expected)) then return nil end
   rate[axis] = observed
  end
  return {status='estimated', first=point(a), second=point(b), velocity=rate,
          unit='sector_distance_per_source_game_second'}
 end
 function api:start()
  if state ~= 'new' or not enter() then return fail('start') end
  deadline = previous_clock + timeout
  local ok, accepted = pcall(sampler_register, sampler,
    {epoch=epoch, index=index, classification='saved_baseline'}, actor)
  if not ok or accepted ~= true or state ~= 'new' then busy=false; return fail('register') end
  state = 'reading'
  return leave()
 end
 function api:tick()
  if state ~= 'reading' or not enter() then return fail('tick') end
  local before, valid_before = request_id()
  if not valid_before then busy=false; return false end
  local ok, accepted = pcall(sampler_tick, sampler)
  if not ok or accepted ~= true or state ~= 'reading' then busy=false; return fail('sampler_tick') end
  local after, valid_after = request_id()
  if not valid_after then busy=false; return false end
  if after and after ~= before then requests = requests + 1 end
  if requests > 8 then busy=false; return fail('request_limit') end
  return leave()
 end
 function api:expected_request()
  if state ~= 'reading' or not enter() then return nil end
  local request, valid = request_id()
  if not valid then busy=false; return nil end
  if not leave() then return nil end
  return request
 end
 function api:event(value)
  if state ~= 'reading' or not enter() then return fail('event') end
  local request, valid = request_id()
  if not valid then busy=false; return false end
  if type(value) ~= 'string' or not request or value:sub(1, #request + 1) ~= request..'|' then
   busy=false; return fail('foreign_event')
  end
  local ok, accepted, sample = pcall(sampler_event, sampler, value)
  if not ok or accepted ~= true or state ~= 'reading' then busy=false; return fail('sampler_event') end
  if sample ~= nil then
   if not first then
    if not plain_sample(sample, 1) or sample.velocity ~= nil then busy=false; return fail('first_sample') end
    first = point(sample)
   else
    if not plain_sample(sample, 2) then busy=false; return fail('second_sample') end
    result = build_result(first, sample)
    if not result then busy=false; return fail('invalid_rate') end
    if delivery and result.status == 'estimated' then
     delivery_sample = {version=sample.version, epoch=sample.epoch, generation=sample.generation,
      index=sample.index, sequence=sample.sequence, sector_macro=sample.sector_macro,
      source_time=sample.source_time, x=sample.x, y=sample.y, z=sample.z,
      velocity={x=sample.velocity.x, y=sample.velocity.y, z=sample.velocity.z}}
    end
    state = 'done'
   end
  end
  return leave()
 end
 function api:result()
  if state ~= 'done' or not enter() then return nil end
  local copy = {status=result.status}
  if result.status == 'estimated' then
   copy.first = point(result.first); copy.second = point(result.second); copy.unit = result.unit
   copy.velocity = {x=result.velocity.x, y=result.velocity.y, z=result.velocity.z}
  else copy.reason = result.reason end
  if not leave() then return nil end
  return copy
 end
 -- This is the checked second sample itself, not a rate for a later pose.
 function api:delivery_sample()
  if not delivery or state ~= 'done' or not enter() then return nil end
  local s = delivery_sample
  local copy = s and {version=s.version, epoch=s.epoch, generation=s.generation, index=s.index,
   sequence=s.sequence, sector_macro=s.sector_macro, source_time=s.source_time,
   x=s.x, y=s.y, z=s.z, velocity={x=s.velocity.x, y=s.velocity.y, z=s.velocity.z}} or nil
  if not leave() then return nil end
  return copy
 end
 function api:stop()
  if state == 'failed' or state == 'stopped' or busy then return fail('stop') end
  if not enter() then return false end
  local request, valid = request_id()
  if not valid then busy=false; return false end
  if request ~= nil then busy=false; return fail('pending_stop') end
  local ok, closed = pcall(sampler_close, sampler)
  if not ok or closed ~= true or not check() then busy=false; return fail('sampler_close') end
  state='stopped'; busy=false
  return true
 end
 function api:state() return state end
 return api
end
X4LAN_AUTHORITY_SOURCE_MOTION_LOCAL_PAIR = M
return M
