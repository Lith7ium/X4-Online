local module = dofile('src/authority/lua/fixture_player_latest_cache.lua')
local grant = {index=3,epoch=string.rep('a',32),generation=string.rep('b',32),
 source=string.rep('c',32),frame=string.rep('d',32),sector='sector_a'}
local function sample(sequence, rate)
 return {version=2,epoch=grant.epoch,generation=grant.generation,index=grant.index,sector_macro=grant.sector,
  sequence=sequence,source_time=sequence / 10,x=sequence,y=2,z=3,
  orientation={yaw=.1,pitch=.2,roll=.3},velocity=rate and {x=10,y=0,z=0} or nil,
  angular_rate=rate and {yaw=0,pitch=0,roll=0} or nil}
end
local function fixture()
 local context={actor='actor',sector=grant.sector,frame=grant.frame,valid=true,controlled=true}
 local tracker={time=0,reset_count=0,authorized=true,guarded=true,quiet=true}
 local options={enabled=true,grant=grant,max_age=1}
 function options.clock() return tracker.time end
 function options.guard() return tracker.guarded end
 function options.authority() return tracker.authorized end
 function options.inspect() return context end
 function options.validate_capture() return true end
 function options.quiescent() return tracker.quiet end
 function options.reset_sampler() tracker.reset_count=tracker.reset_count+1;return true end
 return options,context,tracker
end

-- Local captures 1 and 2 can be superseded; the delivered sequence has no gap.
do
 local options,_,tracker=fixture();local owner=assert(module.new(options))
 assert(owner:capture(sample(1,false)));tracker.time=.1;assert(owner:capture(sample(2,true)))
 tracker.time=.2;assert(owner:capture(sample(3,true)))
 local first,kind=owner:pull()
 assert(kind=='sample' and first.capture_sequence==3 and first.delivery_sequence==1 and
  first.sample.sequence==1 and first.sample.velocity==nil and first.sample.angular_rate==nil)
 local none,empty=owner:pull();assert(none==nil and empty=='empty')
 tracker.time=.3;assert(owner:capture(sample(4,true)))
 local second=assert(owner:pull())
 assert(second.capture_sequence==4 and second.delivery_sequence==2 and second.sample.sequence==2 and
  second.sample.velocity.x==10 and second.sample.angular_rate.yaw==0)
 -- A cache and derivative baseline are discarded before the game pauses.
 tracker.time=.4;assert(owner:capture(sample(5,true)));assert(owner:pause())
 assert(owner:state()=='paused' and tracker.reset_count==1);tracker.time=5
 assert(owner:resume());assert(owner:capture(sample(6,false)))
 tracker.time=5.1;assert(owner:capture(sample(7,true)))
 local resumed=assert(owner:pull())
 assert(resumed.capture_sequence==7 and resumed.delivery_sequence==3 and resumed.sample.velocity==nil)
 tracker.time=5.2;assert(owner:capture(sample(8,true)))
 local next_sample=assert(owner:pull())
 assert(next_sample.capture_sequence==8 and next_sample.delivery_sequence==4 and next_sample.sample.velocity.x==10)
end

-- Expired source-local snapshots are discarded rather than retransmitted.
do
 local options,_,tracker=fixture();local owner=assert(module.new(options));assert(owner:capture(sample(1,false)))
 tracker.time=2;local value,status=owner:pull();assert(value==nil and status=='empty')
 tracker.time=2.1;assert(owner:capture(sample(2,true)))
 local first=assert(owner:pull());assert(first.capture_sequence==2 and first.delivery_sequence==1 and first.sample.velocity==nil)
end

-- A slow final context check may itself exhaust the cached sample's age.
do
 local options,context,tracker=fixture();local inspections=0
 options.inspect=function()
  inspections=inspections+1
  if inspections==5 then tracker.time=2 end
  return context
 end
 local owner=assert(module.new(options));assert(owner:capture(sample(1,false)))
 local value,status=owner:pull();assert(value==nil and status=='empty')
 assert(owner:capture(sample(2,true)))
 local fresh=assert(owner:pull());assert(fresh.capture_sequence==2 and fresh.delivery_sequence==1)
end

for _,scenario in ipairs({'sequence_gap','replay','invalid_rate','context_changed','wrong_frame','grant_lost',
 'guard_lost','mutating_validator','clock_regression','unquiet_pause','reset_failed','pause_rate','reentry'}) do
 local options,context,tracker=fixture();local owner=assert(module.new(options))
 assert(owner:capture(sample(1,false)))
 local success
 if scenario=='sequence_gap' then success=owner:capture(sample(3,true))
 elseif scenario=='replay' then success=owner:capture(sample(1,false))
 elseif scenario=='invalid_rate' then local invalid=sample(2,true);invalid.angular_rate=nil;success=owner:capture(invalid)
 elseif scenario=='context_changed' then context.actor='other';success=owner:capture(sample(2,true))
 elseif scenario=='wrong_frame' then context.frame=string.rep('e',32);success=owner:pull()
 elseif scenario=='grant_lost' then tracker.authorized=false;success=owner:pull()
 elseif scenario=='guard_lost' then tracker.guarded=false;success=owner:pull()
 elseif scenario=='mutating_validator' then
  -- callbacks are captured at construction; build a fresh owner.
  options.validate_capture=function(value) value.x=999;return true end
  owner=assert(module.new(options));success=owner:capture(sample(1,false))
 elseif scenario=='clock_regression' then tracker.time=-1;success=owner:pull()
 elseif scenario=='unquiet_pause' then tracker.quiet=false;success=owner:pause()
 elseif scenario=='reset_failed' then
  options.reset_sampler=function() return false end;owner=assert(module.new(options));success=owner:pause()
 elseif scenario=='pause_rate' then
  assert(owner:pause());assert(owner:resume());success=owner:capture(sample(2,true))
 elseif scenario=='reentry' then
  options.authority=function() owner:pull();return true end
  owner=assert(module.new(options));success=owner:capture(sample(1,false))
 end
 assert(not success and owner:state()=='failed',scenario)
 local again=owner:pull();assert(not again,scenario)
end

-- A context change during the external sample validation cannot commit.
do
 local options,context=fixture()
 options.validate_capture=function() context.actor='different';return true end
 local owner=assert(module.new(options));assert(not owner:capture(sample(1,false)))
 assert(owner:state()=='failed')
end

-- A guard cannot invalidate the inspected actor between observations.
for _,field in ipairs({'valid','controlled','actor','sector','frame'}) do
 local options,context=fixture();local guards=0
 options.guard=function()
  guards=guards+1
  if guards==2 then
   if field=='valid' or field=='controlled' then context[field]=false
   else context[field]='changed' end
  end
  return true
 end
 local owner=assert(module.new(options))
 assert(not owner:capture(sample(1,false)) and owner:state()=='failed',field)
end

-- Losing the grant inside a later guard cannot commit a sample.
do
 local options,_,tracker=fixture();local guards=0
 options.guard=function() guards=guards+1;if guards==2 then tracker.authorized=false end;return true end
 local owner=assert(module.new(options))
 assert(not owner:capture(sample(1,false)) and owner:state()=='failed')
end

-- A quiescence callback cannot revoke the grant before the sampler reset.
do
 local options,_,tracker=fixture()
 options.quiescent=function() tracker.authorized=false;return true end
 local owner=assert(module.new(options))
 assert(not owner:pause() and owner:state()=='failed' and tracker.reset_count==0)
end

-- Even a pause before the first sample pins the original controlled actor.
do
 local options,context=fixture();local owner=assert(module.new(options))
 assert(owner:pause());context.actor='different'
 assert(not owner:resume() and owner:state()=='failed')
end

assert(not module.new({enabled=false}))
