local module=dofile('src/authority/lua/fixture_player_freeze_barrier.lua')

local function fixture()
 local data={time=0,grant=true,pending=2,scheduling=true,resets=0,resumes=0,acks={}}
 local options={enabled=true,timeout=5}
 function options.clock() return data.time end
 function options.guard() return data.grant end
 function options.stop_scheduling() data.scheduling=false;return true end
 function options.quiescent() return data.pending==0 end
 function options.reset_cache() data.resets=data.resets+1;return true end
 function options.resume_cache() data.resumes=data.resumes+1;return true end
 function options.start_scheduling() data.scheduling=true;return true end
 function options.send_ack(kind,id) data.acks[#data.acks+1]={kind,id};return true end
 return options,data
end

-- Two asynchronous events drain across ticks; no reset/ACK happens early.
do
 local options,data=fixture();local barrier=assert(module.new(options))
 local ok,state=barrier:freeze(7);assert(ok and state=='draining' and not data.scheduling)
 ok,state=barrier:tick();assert(ok and state=='waiting' and data.resets==0 and #data.acks==0)
 data.pending=1;ok,state=barrier:tick();assert(ok and state=='waiting' and #data.acks==0)
 data.pending=0;ok,state=barrier:tick()
 assert(ok and state=='frozen' and data.resets==1 and #data.acks==1 and data.acks[1][2]==7)
 -- IDs can skip intervening PULL IDs, but cannot repeat or go backwards.
 data.time=1;ok,state=barrier:resume(10)
 assert(ok and state=='running' and data.resumes==1 and data.scheduling)
 assert(#data.acks==2 and data.acks[2][1]=='resume' and data.acks[2][2]==10)
 assert(barrier:freeze(11));data.pending=0;assert(barrier:tick())
 assert(not barrier:resume(11) and barrier:state()=='failed')
end

for _,scenario in ipairs({'drain_timeout','clock_regression','grant_loss','stop_failure',
 'reset_failure','event_during_reset','freeze_ack_failure','late_freeze_ack',
 'event_after_freeze_ack','reentry'}) do
 local options,data=fixture();local barrier;local ok,reason
 if scenario=='stop_failure' then options.stop_scheduling=function() return false end
 elseif scenario=='reset_failure' then options.reset_cache=function() return false end
 elseif scenario=='event_during_reset' then options.reset_cache=function() data.pending=1;return true end
 elseif scenario=='freeze_ack_failure' then options.send_ack=function() return false end
 elseif scenario=='late_freeze_ack' then options.send_ack=function() data.time=5;return true end
 elseif scenario=='event_after_freeze_ack' then options.send_ack=function() data.pending=1;return true end
 elseif scenario=='reentry' then options.guard=function() if barrier then barrier:tick() end;return true end end
 barrier=assert(module.new(options));ok,reason=barrier:freeze(1)
 if ok then
  if scenario=='drain_timeout' then data.time=5
  elseif scenario=='clock_regression' then data.time=-1
  elseif scenario=='grant_loss' then data.grant=false
  else data.pending=0 end
  ok,reason=barrier:tick()
 end
 assert(not ok and barrier:state()=='failed',scenario)
 if scenario=='freeze_ack_failure' or scenario=='late_freeze_ack' or scenario=='event_after_freeze_ack' then
  assert(reason=='ack_uncertain',scenario)
 elseif scenario=='stop_failure' then assert(reason=='scheduling_uncertain',scenario)
 else assert(reason=='failed',scenario) end
 local count=#data.acks;assert(not barrier:tick() and #data.acks==count,scenario)
end

-- Resume is permitted only when the caller's running-context guard passes.
do
 local options,data=fixture();data.pending=0;local barrier=assert(module.new(options))
 assert(barrier:freeze(1) and barrier:tick());data.grant=false
 local ok=barrier:resume(2);assert(not ok and data.resumes==0 and not data.scheduling)
end

-- After resume ACK, a newly queued packet makes the ACK uncertain and the
-- already enabled scheduler is stopped before returning to the caller.
do
 local options,data=fixture();data.pending=0
 options.send_ack=function(kind)
  if kind=='resume' then data.pending=1 end
  return true
 end
 local barrier=assert(module.new(options));assert(barrier:freeze(1) and barrier:tick())
 local ok,reason=barrier:resume(2)
 assert(not ok and reason=='ack_uncertain' and not data.scheduling and barrier:state()=='failed')
end

-- Lost context after starting scheduling is fenced even before ACK dispatch.
do
 local options,data=fixture();data.pending=0
 options.start_scheduling=function() data.scheduling=true;data.grant=false;return true end
 local barrier=assert(module.new(options));assert(barrier:freeze(1) and barrier:tick())
 local ok,reason=barrier:resume(2)
 assert(not ok and reason=='failed' and not data.scheduling and #data.acks==1)
end

-- If neither the ACK nor scheduling stop can be confirmed, retain both risks.
do
 local options,data=fixture();data.pending=0
 options.send_ack=function(kind) if kind=='resume' then return false end;return true end
 options.stop_scheduling=function()
  if data.resumes>0 then return false end
  data.scheduling=false;return true
 end
 local barrier=assert(module.new(options));assert(barrier:freeze(1) and barrier:tick())
 local ok,reason=barrier:resume(2)
 assert(not ok and reason=='ack_and_scheduling_uncertain' and barrier:state()=='failed')
end

-- Exercise the real standalone cache with the barrier, using fake sampler and MD.
do
 local cache_module=dofile('src/authority/lua/fixture_player_latest_cache.lua')
 local options,data=fixture();data.pending=0
 local grant={index=3,epoch=string.rep('a',32),generation=string.rep('b',32),source=string.rep('c',32),
  frame=string.rep('d',32),sector='sector_a'}
 local resets=0
 local cache=assert(cache_module.new({enabled=true,grant=grant,max_age=1,clock=options.clock,guard=options.guard,
  authority=function()return data.grant end,
  inspect=function()return {actor='actor',sector=grant.sector,frame=grant.frame,valid=true,controlled=true}end,
  validate_capture=function()return true end,quiescent=options.quiescent,
  reset_sampler=function()resets=resets+1;return true end}))
 local function sample(n,rate)
  return {version=2,epoch=grant.epoch,generation=grant.generation,index=3,sector_macro=grant.sector,
   sequence=n,source_time=n,x=n,y=0,z=0,orientation={yaw=0,pitch=0,roll=0},
   velocity=rate and {x=1,y=0,z=0} or nil,angular_rate=rate and {yaw=0,pitch=0,roll=0} or nil}
 end
 assert(cache:capture(sample(1,false)))
 options.reset_cache=function()return cache:pause()end
 options.resume_cache=function()return cache:resume()end
 local barrier=assert(module.new(options));assert(barrier:freeze(1) and barrier:tick())
 assert(resets==1 and cache:state()=='paused')
 assert(barrier:resume(2) and cache:state()=='running')
 assert(cache:capture(sample(2,false)))
 local value=assert(cache:pull());assert(value.delivery_sequence==1 and value.sample.velocity==nil)
end

assert(not module.new({enabled=false}))
