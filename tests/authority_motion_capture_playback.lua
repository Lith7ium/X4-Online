local playback = dofile('src/authority/lua/motion_playback.lua')
local buffer = dofile('src/authority/lua/motion_buffer.lua')

local function sample(sequence, game_time, capture_time, position, rate)
 return {version=3, frame='sector_a', sequence=sequence, source_time=game_time,
  capture_time=capture_time, pose={position,0,0}, real_rate=rate}
end
local function near(actual, expected)
 assert(math.abs(actual-expected)<1e-8, tostring(actual)..' differs from '..tostring(expected))
end
local function track(options)
 options = options or {}
 options.dimensions = 3
 options.clock_basis = 'capture_time'
 options.delay = .1
 options.horizon = .2
 options.stale = .75
 options.clock_leak = 0
 return buffer.new(options)
end

-- Game-time speed and stalls do not change capture-clock reconstruction.
for _,game_rate in ipairs({0,.5,1,2}) do
 local motion = track()
 assert(motion:push(sample(1,100,10,0),1))
 assert(motion:push(sample(2,100+game_rate*.2,10.2,10,{50,0,0}),1.2))
 local rendered = assert(motion:render(1.2))
 assert(rendered.phase=='interpolated')
 near(rendered.pose[1],5)
 rendered = assert(motion:render(1.4))
 near(rendered.pose[1],15)
 rendered = assert(motion:render(1.8))
 assert(rendered.phase=='frozen')
 near(rendered.pose[1],20)
end

-- Missing rates hold the measured pose. The .75 second gap uses capture time.
do
 local motion = track()
 assert(motion:push(sample(1,100,10,0),1))
 assert(motion:push(sample(2,100,10.2,10),1.2))
 local rendered = assert(motion:render(1.5))
 assert(rendered.phase=='held-no-rate' and rendered.pose[1]==10)
 local accepted,reason = motion:push(sample(3,100,11,20,{50,0,0}),2)
 assert(accepted and reason=='gap')
 rendered = assert(motion:render(2.5))
 assert(rendered.phase=='held-no-rate' and rendered.pose[1]==20)
 assert(not motion:push(sample(4,99,11.2,20),2.6))
end

-- Version and rate domains cannot be mixed or silently dropped.
for _,change in ipairs({
 function(value) value.version=1 end,
 function(value) value.capture_time=nil end,
 function(value) value.rate={1,0,0} end,
 function(value) value.orientation={} end,
 function(value) value.real_rate={0/0,0,0} end,
}) do
 local motion = track()
 local value = sample(1,100,10,0)
 change(value)
 assert(not motion:push(value,1))
end
for _,capture_time in ipairs({10,9}) do
 local motion = track()
 assert(motion:push(sample(1,100,10,0),1))
 assert(not motion:push(sample(2,100,capture_time,0),1.2))
end
do
 local legacy = buffer.new({dimensions=3})
 assert(not legacy:push(sample(1,100,10,0),1))
 local old = {version=2,frame='sector_a',sequence=1,source_time=100,pose={0,0,0},rate={1,0,0}}
 assert(legacy:push(old,1)) -- Existing optional legacy version fields remain valid.
 assert(not legacy:push({frame='sector_a',sequence=2,source_time=100,pose={0,0,0}},1.2))
end

-- The legacy derivative helper must never interpret capture-domain samples
-- using their game timestamps. Legacy version 1/2 and absent versions remain valid.
do
 local first = sample(1,100,10,0)
 local second = sample(2,100.2,10.2,10)
 assert(buffer.estimate(first,second,.75)==nil)
 for _,field in ipairs({'capture_time','real_rate'}) do
  local old_first = {frame='sector_a',sequence=1,source_time=100,pose={0,0,0}}
  local old_second = {frame='sector_a',sequence=2,source_time=100.2,pose={10,0,0}}
  old_second[field] = field=='capture_time' and 10.2 or {50,0,0}
  assert(buffer.estimate(old_first,old_second,.75)==nil)
 end
 for _,version in ipairs({false,1,2}) do
  local old_first = {frame='sector_a',sequence=1,source_time=100,pose={0,0,0}}
  local old_second = {frame='sector_a',sequence=2,source_time=100.2,pose={10,0,0}}
  if version then old_first.version=version;old_second.version=version end
  near(assert(buffer.estimate(old_first,old_second,.75))[1],50)
 end
end

-- Capture rates retain the wire's inclusive 5000m/s component bound.
-- The separate legacy rate limit remains unchanged.
for _,rate in ipairs({-5000,5000,-5000.001,5000.001}) do
 local motion = track()
 local accepted = motion:push(sample(1,100,10,0,{rate,0,0}),1)
 assert(accepted==(math.abs(rate)<=5000))
end
do
 local legacy = buffer.new({dimensions=3})
 assert(legacy:push({frame='sector_a',sequence=1,source_time=100,
  pose={0,0,0},rate={100000,0,0}},1))
end

local function controller(change)
 local environment = {now=1, game=10, x=0, writes=0, events={}}
 local options = {enabled=true,sample_version=3,buffer=buffer,frame='sector_a',max_age=1,max_step=50,
  buffer_options={delay=.1,horizon=.2,stale=.75,clock_leak=0},
  clock=function() return environment.now end,
  game=function() return environment.game end,
  paused=function() return false end,
  guard=function() return true end,
  read=function() return {x=environment.x,y=0,z=0,yaw=0,pitch=0,roll=0} end,
  write=function(target) environment.x=target.x;environment.writes=environment.writes+1;return true end,
  record=function(event) environment.events[#environment.events+1]=event;return true end,
  fault=function() end}
 if change then change(options) end
 return assert(playback.new(options)),environment
end

for _,game_rate in ipairs({0,.5,1,2}) do
 local motion,environment = controller()
 assert(motion:push(sample(1,100,10,0),1) and motion:tick())
 environment.now=1.15
 assert(motion:tick())
 environment.now=1.2
 assert(motion:push(sample(2,100+game_rate*.2,10.2,10,{50,0,0}),1.2))
 assert(motion:tick())
 near(environment.x,5)
 local observation = environment.events[#environment.events]
 assert(observation.latest_source_time==100+game_rate*.2 and observation.latest_capture_time==10.2)
 environment.now=1.3
 assert(motion:tick())
 local readback = environment.events[#environment.events-1]
 assert(readback.kind=='readback' and readback.latest_capture_time==10.2)
 assert(readback.latest_source_time==100+game_rate*.2)
end

-- Deferred binding uses original arrival, including its one-second expiry.
do
 local motion,environment = controller()
 assert(motion:push(sample(1,100,10,0),1) and motion:tick())
 environment.now=1.15
 assert(motion:tick())
 environment.now=1.2
 assert(motion:push(sample(2,100,10.2,10),1.1) and motion:tick())
 near(environment.x,5.25) -- The existing lag slew follows the earlier arrival gradually.
 environment.now=2.1
 assert(motion:tick() and motion:state()=='stale')
 local accepted,reason = motion:push(sample(3,100,10.3,20),1.1)
 assert(not accepted and reason=='expired')
end

-- Omitting the opt-in retains the legacy clock domain and rejects v3 input.
do
 local motion,environment = controller(function(options) options.sample_version=nil end)
 assert(not motion:push(sample(1,100,10,0),1))
 assert(motion:state()=='failed' and environment.writes==0)
end

-- Existing correction bound is still inclusive at 50m and rejects larger steps.
for _,position in ipairs({50,50.001}) do
 local motion,environment = controller()
 assert(motion:push(sample(1,100,10,position),1))
 local accepted = motion:tick()
 assert(accepted==(position==50))
 assert(environment.writes==(position==50 and 1 or 0))
end
for _,change in ipairs({
 function(options) options.sample_version=false end,
 function(options) options.sample_version=2 end,
 function(options) options.buffer_options.clock_basis='source_time' end,
}) do assert(not pcall(controller,change)) end
for _,change in ipairs({
 function(value) value.source_time=99 end,
 function(value) value.capture_time=10 end,
 function(value) value.rate={1,0,0} end,
 function(value) value.version=1 end,
}) do
 local motion,environment = controller()
 assert(motion:push(sample(1,100,10,0),1))
 environment.now=1.2
 local value = sample(2,100,10.2,1)
 change(value)
 assert(not motion:push(value,1.2) and motion:state()=='failed' and environment.writes==0)
end
print('capture-clock buffer and playback checks passed')
