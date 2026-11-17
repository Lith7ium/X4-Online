local module = dofile('src/authority/lua/fixture_player_pose_once.lua')
local grant = {index=3, epoch=string.rep('a',32), generation=string.rep('b',32),
 source=string.rep('c',32), sequence=7, sector='sector_one', frame=string.rep('d',32)}
local function copy(value)
 local result = {}; for key, field in pairs(value) do result[key] = field end; return result
end
local function sample()
 local result = copy(grant);result.pose={x=1,y=2,z=3,yaw=.1,pitch=.2,roll=.3};return result
end
local function setup()
 local identity = {actor='ship',sector='local-sector',parent='local-parent',sector_name='sector_one',
  registry_verified=true,registry_index=3,registry_epoch=grant.epoch,
  valid=true,operational=true,is_ship=true,player_context_verified=true,docked=false,stored=false,
  controlled=false,occupied=false,container_ship=false}
 local calls = {writes=0, inspections=0, frames=0}
 local options = {enabled=true,grant=copy(grant)}
 function options.guard() return true end
 function options.inspect(index) assert(index==3);calls.inspections=calls.inspections+1;return copy(identity) end
 function options.frame_attested(request)
  calls.frames=calls.frames+1
  assert(request.frame==grant.frame and request.source==grant.source and request.sequence==7)
  assert(request.local_sector=='local-sector' and request.local_parent=='local-parent')
  return true
 end
 function options.write(actor,sector,pose)
  calls.writes=calls.writes+1
  assert(actor=='ship' and sector=='local-sector' and pose.x==1 and pose.yaw==.1)
  return true
 end
 return options,identity,calls
end

-- One explicitly attested write, followed by a refused second attempt.
do
 local options,_,calls=setup();local owner=assert(module.new(options))
 local ok,result=owner:apply(sample());assert(ok and result=='written' and calls.writes==1)
 assert(calls.inspections==3 and calls.frames==3 and owner:state()=='done')
 assert(not owner:apply(sample()) and calls.writes==1)
end

-- Missing attestation, mismatched grant/sector, and missing player evidence
-- never dispatch the local write.
for _, scenario in ipairs({'disabled','bad_index','bad_source','bad_sequence','bad_frame','bad_sector',
 'nan_pose','unattested','frame_mutation','local_player','unknown_player','docked','stored','invalid_actor',
 'identity_changes','wrong_registry','guard_failure','reentry'}) do
 local options,identity,calls=setup();local candidate=sample();local owner
 if scenario=='disabled' then options.enabled=false;assert(not module.new(options))
 elseif scenario=='bad_index' then candidate.index=4
 elseif scenario=='bad_source' then candidate.source=string.rep('e',32)
 elseif scenario=='bad_sequence' then candidate.sequence=8
 elseif scenario=='bad_frame' then candidate.frame=string.rep('e',32)
 elseif scenario=='bad_sector' then candidate.sector='sector_other'
 elseif scenario=='nan_pose' then candidate.pose.x=0/0
 elseif scenario=='unattested' then options.frame_attested=function() return false end
 elseif scenario=='frame_mutation' then options.frame_attested=function(request) request.frame=string.rep('e',32);return true end
 elseif scenario=='local_player' then identity.occupied='ship'
 elseif scenario=='unknown_player' then identity.player_context_verified=false
 elseif scenario=='docked' then identity.docked=true
 elseif scenario=='stored' then identity.stored=true
 elseif scenario=='invalid_actor' then identity.actor=0
 elseif scenario=='wrong_registry' then identity.registry_index=4
 elseif scenario=='identity_changes' then
  options.inspect=function() calls.inspections=calls.inspections+1;local out=copy(identity)
   if calls.inspections>1 then out.actor='different' end;return out end
 elseif scenario=='guard_failure' then options.guard=function() return false end
 elseif scenario=='reentry' then options.frame_attested=function()
  assert(not owner:apply(sample()));return true end
 end
 if scenario~='disabled' then
  owner=assert(module.new(options));local ok,result=owner:apply(candidate)
  assert(not ok and result=='rejected' and calls.writes==0, scenario)
 end
end

-- Once entered, any writer fault, changed pose or lost frame is uncertain.
for _,scenario in ipairs({'writer_error','writer_mutation','post_frame_loss'}) do
 local options,_,calls=setup()
 if scenario=='writer_error' then options.write=function() calls.writes=calls.writes+1;error('failed') end
 elseif scenario=='writer_mutation' then options.write=function(_,_,pose) calls.writes=calls.writes+1;pose.x=2;return true end
 else options.frame_attested=function() calls.frames=calls.frames+1;return calls.frames<3 end end
 local owner=assert(module.new(options));local ok,result=owner:apply(sample())
 assert(not ok and result=='uncertain' and calls.writes==1,scenario)
 assert(not owner:apply(sample()) and calls.writes==1)
end

-- Untrusted Lua tables must not throw out of the owner or reach the writer.
for _,where in ipairs({'sample','pose','inspect'}) do
 local options,_,calls=setup();local candidate=sample()
 local hostile=setmetatable({}, {__index=function() error('hostile index') end})
 if where=='sample' then candidate=hostile
 elseif where=='pose' then candidate.pose=hostile
 else options.inspect=function() return hostile end end
 local owner=assert(module.new(options));local ok,result=owner:apply(candidate)
 assert(not ok and result=='rejected' and calls.writes==0 and owner:state()=='failed',where)
end

-- Second registered slot is accepted only under its own explicit grant.
do
 local options,_,calls=setup();options.grant.index=4
 local original=options.inspect;options.inspect=function(index) assert(index==4);local value=original(3);value.registry_index=4;return value end
 local candidate=sample();candidate.index=4
 local owner=assert(module.new(options));assert(owner:apply(candidate) and calls.writes==1)
end
