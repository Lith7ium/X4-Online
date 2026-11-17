-- Engine-free state-machine checks; this does not test real MD or X4 flight.
local function fixture()
 local time, active, sent, messages = 0, true, {}, {}
 local module = dofile('tools/dev/authority_fixture_client_throttle.lua')
 assert(module.new({enabled=false}) == nil)
 local cfg = {enabled=true, epoch=string.rep('a',32), nonce=string.rep('b',32), slot=2, timeout=5,
  clock=function() return time end, guard=function() return active end,
  dispatch=function(screen, control, value)
   sent[#sent+1]={screen=screen,control=control,value=value}; return true
  end,
  log=function(value) messages[#messages+1]=value; return true end}
 local owner = assert(module.new(cfg)); assert(module.new(cfg) == nil)
 local receipt=cfg.nonce..'|'..cfg.epoch..'|2'
 return {owner=owner, options=cfg, sent=sent, messages=messages, receipt=receipt,
  set_time=function(v)time=v end, set_active=function(v)active=v end}
end
local f=fixture();assert(f.owner:start()); assert(#f.sent==1)
assert(f.sent[1].screen=='X4AuthorityFixtureClientThrottle' and f.sent[1].control=='Start')
assert(f.owner:status().effect_uncertain and f.owner:started(f.receipt))
f.set_time(1);assert(f.owner:tick());assert(f.owner:stopped(f.receipt))
local status=f.owner:status();assert(status.state=='done' and status.start_attempted and status.stop_acknowledged)
assert(not status.effect_uncertain and not status.stopped_movement_proven and not status.real_input_proven)
assert(#f.sent==1 and #f.messages==3 and f.owner:tick())
-- Failure before dispatch is rejected, after dispatch it is uncertain.
f=fixture();f.set_active(false);local ok,reason=f.owner:start()
assert(not ok and reason=='rejected' and #f.sent==0 and not f.owner:status().start_attempted)
f=fixture();assert(f.owner:start());f.set_active(false);ok,reason=f.owner:started(f.receipt)
assert(not ok and reason=='uncertain' and f.owner:status().effect_uncertain)
-- A missing stop, stale/foreign receipt or failed guard never allows retry.
f=fixture();assert(f.owner:start());assert(f.owner:started(f.receipt));f.set_time(5)
ok,reason=f.owner:tick();assert(not ok and reason=='uncertain')
assert(not f.owner:start() and #f.sent==1 and not f.owner:status().stop_acknowledged)
f=fixture();assert(f.owner:start());assert(not f.owner:started(f.receipt..'bad'))
assert(f.owner:status().effect_uncertain and not f.owner:start() and #f.sent==1)
f=fixture();assert(f.owner:start());assert(not f.owner:stopped(f.receipt))
assert(f.owner:status().effect_uncertain and #f.sent==1)
-- A dispatch failure may have occurred after the native action entered.
f=fixture();f.options.dispatch=function() error('partial dispatch') end
-- Options are copied when constructed; a fresh owner uses the new callback.
f.owner=assert(dofile('tools/dev/authority_fixture_client_throttle.lua').new(f.options))
ok,reason=f.owner:start();assert(not ok and reason=='uncertain' and f.owner:status().start_attempted)
-- Reentrant event delivery is fenced even when the dispatcher suppresses it.
f=fixture();local owner
f.options.dispatch=function() owner:started(f.receipt);return true end
owner=assert(dofile('tools/dev/authority_fixture_client_throttle.lua').new(f.options))
ok,reason=owner:start();assert(not ok and reason=='uncertain' and owner:status().state=='failed')
-- The second guard may be slow: expiry still fences dispatch or a stop ACK.
f=fixture();local guard_calls=0
f.options.guard=function() guard_calls=guard_calls+1; if guard_calls==4 then f.set_time(6) end;return true end
owner=assert(dofile('tools/dev/authority_fixture_client_throttle.lua').new(f.options))
ok,reason=owner:start();assert(not ok and reason=='rejected' and #f.sent==0)
f=fixture();guard_calls=0
f.options.guard=function() guard_calls=guard_calls+1; if guard_calls==2 then f.set_time(6) end;return true end
-- Arm the slow guard only for stop, after successful start and STARTED.
local slow=f.options.guard; f.options.guard=function() return true end
local slow_enabled=false
f.options.guard=function() if slow_enabled then return slow() end;return true end
owner=assert(dofile('tools/dev/authority_fixture_client_throttle.lua').new(f.options))
assert(owner:start());assert(owner:started(f.receipt));slow_enabled=true
ok,reason=owner:stopped(f.receipt);assert(not ok and reason=='uncertain' and not owner:status().stop_acknowledged)
-- Going backward in the monotonic clock is rejected.
f=fixture();f.set_time(2);assert(f.owner:start());f.set_time(1)
assert(not f.owner:started(f.receipt) and f.owner:status().effect_uncertain)
print('fixture client throttle synthetic fences passed')
