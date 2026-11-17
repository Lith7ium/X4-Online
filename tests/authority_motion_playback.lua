local playback = dofile('src/authority/lua/motion_playback.lua')
local buffer = dofile('src/authority/lua/motion_buffer.lua')

local function rig(change)
 local actual = {x=0,y=0,z=0,yaw=.7,pitch=.2,roll=.1}
 local environment = {now=1, game=10, paused=false, reads=0, writes=0, events={}, faults={}}
 local controller
 local options = {enabled=true, buffer=buffer, frame='sector_a', max_age=1, max_step=100,
  buffer_options={delay=.1,horizon=.2,stale=.75},
  clock=function() return environment.now end, game=function() return environment.game end,
  paused=function() return environment.paused end, guard=function() return true end,
  read=function() environment.reads=environment.reads+1; return actual end,
  write=function(target)
   environment.writes=environment.writes+1
   assert(target.yaw==actual.yaw and target.pitch==actual.pitch and target.roll==actual.roll)
   actual.x,actual.y,actual.z=target.x,target.y,target.z
   return true
  end,
  record=function(event) environment.events[#environment.events+1]=event; return true end,
  fault=function(reason,uncertain) environment.faults[#environment.faults+1]={reason,uncertain} end}
 if change then change(options,environment,actual,function() return controller end) end
 controller = assert(playback.new(options))
 local function sample(sequence,x,source)
  return {frame='sector_a',sequence=sequence,source_time=source or (100000+sequence*.2),pose={x,0,0}}
 end
 return controller,environment,actual,sample
end

-- Static targets still read real drift. Previous write is measured before the next write.
do
 local controller,environment,actual,sample=rig()
 assert(controller:push(sample(1,10),1) and controller:tick())
 assert(environment.writes==1 and controller:outcome_uncertain())
 actual.x=4; environment.now=1.1
 assert(controller:tick() and environment.writes==2 and environment.reads==2)
 assert(environment.events[2].kind=='readback' and environment.events[2].actual.x==4 and environment.events[2].error==6)
 assert(environment.events[3].kind=='observation')
 environment.now=1.2; assert(controller:tick() and environment.writes==2 and not controller:outcome_uncertain())
end

-- Real buffering interpolates, tolerates deferred arrival and bounds extrapolation.
do
 local controller,environment,actual,sample=rig()
 assert(controller:push(sample(1,0,8000),1)); assert(controller:tick())
 environment.now=1.15; assert(controller:tick())
 assert(controller:push(sample(2,20,8000.2),1.1)) -- receive preceded the last rendered frame
 environment.now=1.2; assert(controller:tick())
 assert(actual.x>0 and actual.x<20)
 local events=environment.events; assert(events[#events].phase=='interpolated')
 local third=sample(3,30,8000.3); third.rate={100,0,0}
 environment.now=1.3; assert(controller:push(third,1.3))
 environment.now=1.9; assert(controller:tick() and actual.x<=50.000001)
end

-- Local age stops writes, while a strictly newer fresh sample may recover.
do
 local controller,environment,actual,sample=rig()
 assert(controller:push(sample(1,10),1) and controller:tick())
 environment.now=2.1; actual.x=7
 assert(controller:tick() and environment.writes==1 and controller:state()=='stale')
 local accepted,reason=controller:push(sample(2,20),1.05)
 assert(not accepted and reason=='expired' and environment.writes==1)
 environment.now=2.2; assert(controller:push(sample(2,20),2.2) and controller:tick())
 assert(environment.writes==2 and actual.x==20)
 assert(not controller:push(sample(1,10),2.2) and controller:state()=='failed')
end

-- Pause does not inspect/write; old queued arrivals cannot revive invalidated samples.
do
 local controller,environment,actual,sample=rig()
 assert(controller:push(sample(1,10),1) and controller:tick())
 local reads=environment.reads
 environment.now=1.1; environment.paused=true
 assert(controller:tick() and environment.reads==reads and environment.writes==1)
 assert(controller:outcome_uncertain()) -- No readback was invented while paused.
 environment.now=1.2; environment.paused=false
 assert(controller:tick() and environment.writes==1)
 local accepted,reason=controller:push(sample(2,20),1.15) -- Received during pause, bound after resume.
 assert(not accepted and reason=='expired')
 environment.now=1.3; assert(controller:push(sample(2,20),1.3) and controller:tick())
 assert(actual.x==20 and controller:stop())
 environment.now=1.4; assert(controller:tick() and environment.writes==2)
 assert(not controller:push(sample(3,30),1.4) and environment.writes==2)
end

for _,failure in ipairs({'write','reentrant','frame'}) do
 local controller,environment,actual,sample=rig(function(options,env,pose,get_controller)
  if failure=='write' then options.write=function(target) env.writes=env.writes+1;pose.x=target.x;error('partial effect') end end
  if failure=='reentrant' then options.write=function() env.writes=env.writes+1;get_controller():tick();return true end end
 end)
 local first=sample(1,10)
 if failure=='frame' then first.frame='other';assert(not controller:push(first,1) and environment.writes==0)
 else
  assert(controller:push(first,1));assert(not controller:tick() and environment.writes==1 and controller:outcome_uncertain())
 end
 controller:stop(); environment.now=1.2
 assert(not controller:tick() and environment.writes<2)
end

-- Losing an external guard or stopping from a record callback cannot write again.
for _,mode in ipairs({'guard_lost','record_stop'}) do
 local allowed=true
 local controller,environment,actual,sample=rig(function(options,env,pose,get_controller)
  options.guard=function()return allowed end
  if mode=='record_stop' then
   options.record=function(event)
    if env.writes>0 then get_controller():stop() end
    return true
   end
  end
 end)
 assert(controller:push(sample(1,10),1) and controller:tick() and environment.writes==1)
 actual.x=3;environment.now=1.1
 if mode=='guard_lost' then allowed=false end
 assert(not controller:tick() and environment.writes==1)
 assert(controller:outcome_uncertain() and controller:state()=='failed')
 environment.now=1.2;assert(not controller:tick() and environment.writes==1)
end

-- Old buffer behavior remains strict unless deferred arrival is explicitly enabled.
do
 local track=buffer.new({dimensions=3})
 assert(track:push({frame='a',sequence=1,source_time=1,pose={0,0,0}},1));assert(track:render(2))
 assert(not track:push({frame='a',sequence=2,source_time=2,pose={1,0,0}},1.5))
end
print('real motion buffer playback, measured drift and lifecycle checks passed')
