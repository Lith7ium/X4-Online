-- Default-off one-shot throttle diagnostic for a disposable fixture client.
-- The owner must bind callbacks to the owned process, seat and update loop.
local M = {}
local constructed = false

local function token(value)
 return type(value) == 'string' and #value == 32 and value:match('^[0-9a-f]+$') ~= nil
end
local function finite(value)
 return type(value) == 'number' and value == value and math.abs(value) < math.huge
end

function M.new(options)
 if type(options) ~= 'table' or options.enabled ~= true then return nil, 'disabled' end
 if constructed then return nil, 'already_constructed' end
 assert(token(options.epoch) and token(options.nonce) and options.epoch ~= options.nonce)
 assert(options.slot == 1 or options.slot == 2)
 assert(finite(options.timeout) and options.timeout >= 3 and options.timeout <= 15)
 for _, key in ipairs({'clock', 'guard', 'dispatch', 'log'}) do assert(type(options[key]) == 'function') end
 local config = {epoch=options.epoch, nonce=options.nonce, slot=options.slot, timeout=options.timeout,
  clock=options.clock, guard=options.guard, dispatch=options.dispatch, log=options.log}
 constructed = true
 local state, busy, attempted, stop_confirmed = 'new', false, false, false
 local deadline, last_time = nil, nil
 local api = {}
 local function fail()
  state = 'failed'
  return false, attempted and 'uncertain' or 'rejected'
 end
 local function check(expected)
  assert(state == expected and config.guard() == true and state == expected)
  local now = config.clock()
  assert(state == expected and finite(now) and now >= 0 and (last_time == nil or now >= last_time)
   and (deadline == nil or now < deadline))
  last_time = now
  assert(config.guard() == true and state == expected)
  now = config.clock()
  assert(state == expected and finite(now) and now >= last_time and (deadline == nil or now < deadline))
  last_time = now
  return now
 end
 local function action(body)
  if busy or state == 'failed' or state == 'done' then return fail() end
  busy = true
  local ok = pcall(body)
  busy = false
  if not ok or state == 'failed' then return fail() end
  return true, state
 end
 local function receipt(value)
  return value == config.nonce .. '|' .. config.epoch .. '|' .. tostring(config.slot)
 end
 function api:start()
  return action(function()
   assert(state == 'new')
   local now = check('new'); deadline = now + config.timeout
   assert(config.log('START_INTENT ' .. config.nonce) == true)
   check('new')
   state = 'starting'
   attempted = true -- dispatch may have reached X4 even if it raises
   assert(config.dispatch('X4AuthorityFixtureClientThrottle', 'Start',
    {request_id=config.nonce, epoch=config.epoch, slot=config.slot}) == true)
   check('starting')
  end)
 end
 function api:started(value)
  return action(function()
   check('starting'); assert(receipt(value))
   assert(config.log('STARTED ' .. config.nonce) == true)
   check('starting'); state = 'running'
  end)
 end
 function api:stopped(value)
  return action(function()
   check('running'); assert(receipt(value))
   assert(config.log('STOPPED ' .. config.nonce) == true)
   check('running'); stop_confirmed = true; state = 'done'
  end)
 end
 function api:refused()
  return fail()
 end
 function api:tick()
  if state == 'done' then return true, 'done' end
  return action(function()
   assert(state == 'new' or state == 'starting' or state == 'running')
   check(state)
  end)
 end
 function api:status()
  return {state=state, start_attempted=attempted, stop_acknowledged=stop_confirmed,
   effect_uncertain=attempted and not stop_confirmed, stopped_movement_proven=false,
   real_input_proven=false}
 end
 return api
end
X4LAN_FIXTURE_CLIENT_THROTTLE = M
return M
