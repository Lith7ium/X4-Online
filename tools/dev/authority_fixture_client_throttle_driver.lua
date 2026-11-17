-- Private, one-shot command bridge on its own loopback socket.
local M = {}
function M.new(cfg, net, guard, paused, game_time)
 assert(type(cfg)=='table' and type(guard)=='function' and type(paused)=='function' and type(game_time)=='function')
 local prefix = cfg.throttle_lease .. '|' .. cfg.throttle_attempt .. '|' .. cfg.epoch .. '|' ..
  cfg.generation .. '|' .. cfg.throttle_nonce .. '|' .. tostring(cfg.slot)
 local state, owner = 'new', nil
 local function fail() state='failed'; return false end
 local function send(kind)
  assert(net:send(kind .. '|' .. prefix) == true)
 end
 owner = assert(X4LAN_FIXTURE_CLIENT_THROTTLE.new({enabled=true, epoch=cfg.epoch, nonce=cfg.throttle_nonce,
  slot=cfg.slot, timeout=cfg.throttle_timeout, clock=GetCurRealTime,
  guard=function() return guard() == true and X4LAN_FIXTURE_SEAT_READY == true and not paused() end,
  dispatch=function(screen, control, value) return AddUITriggeredEvent(screen, control, value) ~= false end,
  log=function(value) DebugError('[X4LAN] AUTH_FIXTURE_CLIENT_THROTTLE ' .. value); return true end}))
 RegisterEvent('X4AuthorityFixtureClientThrottle.Started', function(_, value)
  if state~='starting' or not owner:started(value) then fail(); return end
  local ok = pcall(send, 'STARTED'); if not ok then fail(); return end
  state='running'
 end)
 RegisterEvent('X4AuthorityFixtureClientThrottle.Stopped', function(_, value)
  if state~='running' or not owner:stopped(value) then fail(); return end
  local ok = pcall(function()
   assert(guard() == true and X4LAN_FIXTURE_SEAT_READY == true and not paused())
   local stopped_at = game_time()
   assert(type(stopped_at)=='number' and stopped_at==stopped_at and stopped_at>=0 and stopped_at<=1e12)
   assert(guard() == true and X4LAN_FIXTURE_SEAT_READY == true and not paused())
   assert(net:send('STOPPED|' .. prefix .. '|' .. string.format('%.17g', stopped_at)) == true)
  end)
  if not ok then fail(); return end
  state='done'
 end)
 RegisterEvent('X4AuthorityFixtureClientThrottle.Refused', function() owner:refused(); fail() end)
 local api={}
 function api:tick()
  if state=='failed' then return false end
  local ok = pcall(function()
   if state=='new' then
    if paused() then return end
    assert(guard() == true and X4LAN_FIXTURE_SEAT_READY == true)
    send('READY'); state='ready'
   elseif state=='ready' then
    if paused() then assert(net:pending()==false); return end
    assert(guard() == true and X4LAN_FIXTURE_SEAT_READY == true)
    local waiting=net:pending(); assert(type(waiting)=='boolean')
    if not waiting then return end
    assert(net:receive()=='GO|'..prefix and net:pending()==false)
    state='starting'; assert(owner:start())
   elseif state=='starting' or state=='running' then
    assert(net:pending()==false and owner:tick())
   elseif state=='done' then
    assert(net:pending()==false)
   else error('invalid throttle state') end
  end)
  if not ok then return fail() end
  return state~='failed'
 end
 function api:status() return owner:status() end
 return api
end
X4LAN_FIXTURE_CLIENT_THROTTLE_DRIVER = M
return M
