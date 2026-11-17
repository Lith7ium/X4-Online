-- LuaJIT synthetic ABI and MD events only; no native X4 is started.
local function scenario(name)
 local events, packets, replies = {}, {}, {}
 local writes, clock, guard_count = 0, 1, 0
 local intent, setter_entered = false, false
 local pose = {x=100,y=20,z=30,yaw=.1,pitch=.2,roll=.3}
 local paused = false
 local C = {}
 function C.GetSaveFolderPath() return '/tmp/private/45841/save' end
 function C.IsPlayerValid() return true end
 function C.IsGamePaused() return paused end
 function C.IsValidComponent(id) return id ~= 0 end
 function C.IsComponentOperational() return true end
 function C.IsComponentClass(id, class) return (id==101 and class=='ship') or (id==102 and class=='sector') or (id==103 and class=='zone') end
 function C.GetContextByClass(id, class)
  if id==101 and class=='sector' then return 102 end
  if id==101 and class=='zone' then return 103 end
  if id==104 and class=='station' then return 104 end
  return 0
 end
 function C.GetPlayerControlledShipID() return name=='player' and 101 or 0 end
 function C.GetPlayerOccupiedShipID() return 0 end
 function C.GetPlayerContainerID() return 104 end
 function C.GetObjectPositionInSector() return pose end
 function C.SetObjectSectorPos(actor, sector, target)
  assert(actor==101 and sector==102 and math.abs(target.yaw-.1*180/math.pi)<1e-8)
  writes = writes + 1; setter_entered = true
  if name=='setter_error' then error('setter may have written') end
  pose = {x=target.x,y=target.y,z=target.z,yaw=.1,pitch=.2,roll=.3}
 end
 package.loaded.ffi = {C=C, NULL={}, typeof=function() return true end, cdef=function() end,
  string=function(value) return value end, new=function(_, value) return value end}
 X4LAN_RESOLVE_STRING={parse_hex=function(value) return tonumber(value) end, actor_u64=function(value) return value~=0 and value or nil end}
 X4LAN_AUTHORITY_MARKER_READY=function() return true end
 ConvertStringToLuaID=function(value) return tonumber(value) end
 ConvertIDTo64Bit=function(value) return value end
 GetCurRealTime=function() return clock end
 GetComponentData=function(id, field)
  if field=='isdocked' then return name=='docked',false,false end
  if field=='macro' and id==101 then return 'ship_arg_s_fighter_01_a_macro','player' end
  if field=='macro' and id==102 then return name=='slot2' and 'cluster_45_sector001_macro' or 'cluster_33_sector001_macro' end
  error('unexpected GetComponentData')
 end
 RegisterEvent=function(event, callback) events[event]=callback;return true end
 AddUITriggeredEvent=function(screen, control, payload)
  assert(screen=='X4AuthorityFixtureLocalOffset' and control=='Inspect'); return true
 end
 local net = {}
 function net:send(value) replies[#replies+1]=value;return true end
 function net:pending()
  if name=='deadline_pending' and intent then clock=12 end
  return #packets>0
 end
 function net:receive() return table.remove(packets,1) end
 local slot = name=='slot2' and 2 or 1
 local options={enabled=true,epoch=string.rep('a',32),nonce=string.rep('b',32),generation=string.rep('c',32),
  lease=string.rep('d',32),attempt=string.rep('e',32),slot=slot,net=net,
  expected_save_path='/tmp/private/45841/save',timeout=10,guard=function()
   if (name=='deadline_pre' and intent) or (name=='deadline_after' and setter_entered) then
    guard_count = guard_count + 1
    if guard_count == 2 then clock = 12 end
   end
   return true
  end,
  log=function(line) if line:match('^WRITE_ENTERED ') then intent=true end; return true end}
 local module=dofile('tools/dev/authority_fixture_player_sample_writer.lua')
 assert(not module.new({enabled=false}))
 local owner=assert(module.new(options));assert(not module.new(options));assert(owner:tick())
 if name=='paused_stale' then paused=true; assert(owner:tick()); paused=false end
 local sector=slot==1 and 'cluster_33_sector001_macro' or 'cluster_45_sector001_macro'
 local target=name=='near' and '100' or name=='far' and '151' or '110'
 local fields={'P',options.lease,options.attempt,'WRITE',string.rep('f',32),options.epoch,
  name=='wrong_generation' and string.rep('9',32) or options.generation,tostring(slot+2),'7',sector,string.rep('a',64),target,'20','30'}
 if name=='wrong_sector' then fields[10]='foreign_sector' end
 packets[1]=table.concat(fields,'|')
 local ok=owner:tick()
 if name=='wrong_generation' or name=='wrong_sector' or name=='paused_stale' then assert(not ok and writes==0);return end
 assert(ok and owner:state()=='pre')
 local function respond(phase, actor)
  events['X4AuthorityFixtureLocalOffset.Result'](nil,options.nonce..phase..'|'..options.epoch..'|'..(slot+2)..'|'..(actor or '0x65')..'|0x66|0x67')
 end
 if name=='pause' then paused=true end
 if name=='queued_during_md' then packets[1]='unexpected' end
 respond('1',name=='wrong_actor' and '0x68' or nil)
 if name=='player' or name=='docked' or name=='near' or name=='far' or name=='pause' or name=='wrong_actor' or name=='deadline_pre' or name=='queued_during_md' or name=='deadline_pending' then
  assert(owner:state()=='failed' and writes==0,name);return
 end
 if name=='setter_error' or name=='deadline_after' then assert(owner:state()=='failed' and writes==1);assert(not owner:tick() and writes==1);return end
 assert(owner:state()=='post_pending' and writes==1);assert(owner:tick());respond('2',name=='wrong_post' and '0x68' or nil)
 if name=='wrong_post' then assert(owner:state()=='failed' and writes==1 and #replies==1);return end
 assert(owner:state()=='done' and writes==1)
 assert(replies[2]:match('^R|'..options.lease..'|'..options.attempt..'|RESULT|'))
 assert(owner:result().before.x==100 and owner:result().after.x==110)
 assert(owner:tick() and writes==1)
end
for _,name in ipairs({'normal','slot2','player','docked','near','far','pause','wrong_actor','wrong_post','queued_during_md','deadline_pending','deadline_pre','deadline_after','paused_stale','wrong_generation','wrong_sector','setter_error'}) do scenario(name) end
