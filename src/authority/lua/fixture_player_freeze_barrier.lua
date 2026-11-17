-- Offline, default-off freeze/drain state machine. No X4 or network bindings.
-- The caller owns the single event route, the actual UDP protocol and X4 pause.
local M = {}
local MAX_INTEGER = 9007199254740991

local function finite(value, limit)
 return type(value) == 'number' and value == value and math.abs(value) <= limit
end
local function request_id(value)
 return finite(value, MAX_INTEGER) and value >= 1 and value % 1 == 0
end

function M.new(options)
 if type(options) ~= 'table' or getmetatable(options) ~= nil or options.enabled ~= true then
  return nil, 'disabled'
 end
 if not finite(options.timeout, 120) or options.timeout <= 0 then return nil, 'invalid_timeout' end
 for _, name in ipairs({'clock', 'guard', 'stop_scheduling', 'quiescent', 'reset_cache',
                        'resume_cache', 'start_scheduling', 'send_ack'}) do
  if type(options[name]) ~= 'function' then return nil, 'missing_callback' end
 end
 local clock, guard = options.clock, options.guard
 local stop_scheduling, quiescent, reset_cache = options.stop_scheduling, options.quiescent, options.reset_cache
 local resume_cache, start_scheduling, send_ack = options.resume_cache, options.start_scheduling, options.send_ack
 local timeout = options.timeout
 local state, busy = 'running', false
 local last_clock, deadline, last_request, current_request = nil, nil, 0, nil
 local ack_attempted = false
 local stopping, stop_reentered = false, false
 local api = {}

 local function fail()
  if stopping then stop_reentered = true;return false, 'scheduling_uncertain' end
  state = 'failed';busy = true;stopping = true;stop_reentered = false
  -- The callback must synchronously fence this owner's scheduling flag even
  -- after the surrounding grant or running-context guard has failed.
  local stopped, result = pcall(stop_scheduling)
  stopping = false;busy = false
  if not stopped or result ~= true or stop_reentered then
   return false, ack_attempted and 'ack_and_scheduling_uncertain' or 'scheduling_uncertain'
  end
  return false, ack_attempted and 'ack_uncertain' or 'failed'
 end
 local function time_now()
  local value = clock()
  if not finite(value, 1e12) or value < 0 or (last_clock and value < last_clock) then return nil end
  last_clock = value
  return value
 end
 local function checked(expected)
  local before = time_now()
  if not before or not deadline or before >= deadline or state ~= expected then return false end
  if guard() ~= true or state ~= expected then return false end
  local after = time_now()
  return after ~= nil and after >= before and after < deadline and state == expected
 end
 local function begin(expected, id, next_state)
  if busy or state ~= expected or not request_id(id) or id <= last_request then return false end
  busy = true;state = next_state;current_request = id;last_request = id;ack_attempted = false
  local now = time_now()
  if not now then return false end
  deadline = now + timeout
  return finite(deadline, 1e12) and checked(next_state)
 end
 local function acknowledge(kind, expected)
  if not checked(expected) then return false end
  -- A failed, interrupted or late send may still have reached the peer.
  ack_attempted = true
  if send_ack(kind, current_request) ~= true then return false end
  return checked(expected)
 end

 function api:freeze(id)
  local ok, result = pcall(function()
   if not begin('running', id, 'draining') then return false end
   if stop_scheduling() ~= true or not checked('draining') then return false end
   return true
  end)
  if not ok or result ~= true then return fail() end
  busy = false;return true, 'draining'
 end

 function api:tick()
  if busy or state ~= 'draining' then return fail() end
  busy = true
  local ok, result = pcall(function()
   if not checked('draining') then return nil end
   local quiet = quiescent()
   if (quiet ~= true and quiet ~= false) or not checked('draining') then return nil end
   if not quiet then return 'waiting' end
   state = 'finalizing'
   if not checked('finalizing') or reset_cache() ~= true or not checked('finalizing') then return nil end
   if quiescent() ~= true or not checked('finalizing') then return nil end
   if not acknowledge('freeze', 'finalizing') then return nil end
   if quiescent() ~= true or not checked('finalizing') then return nil end
   state = 'frozen';deadline = nil;current_request = nil;ack_attempted = false
   return 'frozen'
  end)
  if not ok or not result then return fail() end
  busy = false;return true, result
 end

 function api:resume(id)
  -- The caller must first confirm that local X4 has resumed under this grant.
  local ok, result = pcall(function()
   if not begin('frozen', id, 'resuming') then return false end
   if quiescent() ~= true or not checked('resuming') or resume_cache() ~= true or
    not checked('resuming') or quiescent() ~= true or not checked('resuming') then return false end
   if start_scheduling() ~= true or not checked('resuming') then return false end
   if not acknowledge('resume', 'resuming') then return false end
   if quiescent() ~= true or not checked('resuming') then return false end
   state = 'running';deadline = nil;current_request = nil;ack_attempted = false
   return true
  end)
  if not ok or result ~= true then return fail() end
  busy = false;return true, 'running'
 end

 function api:state() return state end
 return api
end

X4LAN_FIXTURE_PLAYER_FREEZE_BARRIER=M
return M
