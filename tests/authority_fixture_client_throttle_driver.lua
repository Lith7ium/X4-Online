-- Simulated client update/event wiring, no X4 process or native MD.
local events, sent, queued, dispatched, paused = {}, {}, {}, 0, false
X4LAN_FIXTURE_SEAT_READY = true
X4LAN_FIXTURE_CLIENT_THROTTLE = dofile('tools/dev/authority_fixture_client_throttle.lua')
RegisterEvent=function(name, fn) events[name]=fn; return true end
GetCurRealTime=function() return 1 end
DebugError=function() end
AddUITriggeredEvent=function(screen, control, request)
 assert(screen=='X4AuthorityFixtureClientThrottle' and control=='Start' and request.slot==2)
 dispatched=dispatched+1;return true
end
local cfg={epoch=string.rep('a',32), generation=string.rep('b',32), throttle_lease=string.rep('c',32),
 throttle_attempt=string.rep('d',32), throttle_nonce=string.rep('e',32), slot=2, throttle_timeout=10}
local net={send=function(_, packet)sent[#sent+1]=packet;return true end,
 pending=function()return #queued>0 end,receive=function()return table.remove(queued,1)end}
local module=dofile('tools/dev/authority_fixture_client_throttle_driver.lua')
local driver=module.new(cfg,net,function()return true end,function()return paused end,function()return 42.5 end)
assert(driver:tick() and #sent==1 and sent[1]:match('^READY|'))
assert(driver:tick() and dispatched==0)
queued[1]=sent[1]:gsub('^READY|','GO|')
assert(driver:tick() and dispatched==1)
local receipt=cfg.throttle_nonce..'|'..cfg.epoch..'|2'
events['X4AuthorityFixtureClientThrottle.Started'](nil,receipt)
assert(#sent==2 and sent[2]:match('^STARTED|'))
events['X4AuthorityFixtureClientThrottle.Stopped'](nil,receipt)
assert(#sent==3 and sent[3]:match('^STOPPED|') and sent[3]:match('|42%.5$'))
assert(driver:tick() and driver:status().stop_acknowledged and dispatched==1)
queued[1]=sent[1]:gsub('^READY|','GO|')
assert(not driver:tick() and dispatched==1)
print('fixture throttle client driver synthetic path passed')
