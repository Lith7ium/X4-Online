-- Synthetic native ABI only: does not execute or validate X4 itself.
local function scenario(name)
 local events, logs, issued, writes = {}, {}, {}, 0
 local pose = {x=100,y=20,z=30,yaw=.1,pitch=.2,roll=.3}
 local active = true
 local C = {}
 function C.GetSaveFolderPath() return '/tmp/private/45841/save' end
 function C.IsPlayerValid() return true end
 function C.IsGamePaused() return true end
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
  writes = writes + 1
  if name=='write_error' then error('partial native write') end
  pose = {x=target.x,y=target.y,z=target.z,yaw=.1,pitch=.2,roll=.3}
 end
 package.loaded.ffi = {C=C, NULL={}, typeof=function() return true end, cdef=function() end,
  string=function(value) return value end, new=function(_, value) return value end}
 X4LAN_RESOLVE_STRING={parse_hex=function(value) return tonumber(value) end, actor_u64=function(value) return value~=0 and value or nil end}
 X4LAN_AUTHORITY_MARKER_READY=function() return true end
 ConvertStringToLuaID=function(value) return tonumber(value) end
 ConvertIDTo64Bit=function(value) return value end
 GetCurRealTime=function() return 1 end
 GetComponentData=function(id, field)
  if field=='isdocked' then return name=='docked',false,false end
  if field=='macro' and id==101 then return 'ship_arg_s_fighter_01_a_macro','player' end
  if field=='macro' and id==102 then return name=='slot2' and 'cluster_45_sector001_macro' or 'cluster_33_sector001_macro' end
  error('unexpected GetComponentData')
 end
 RegisterEvent=function(event, callback) events[event]=callback; return true end
 AddUITriggeredEvent=function(screen, control, payload)
  assert(screen=='X4AuthorityFixtureLocalOffset' and control=='Inspect')
  issued[#issued+1]=payload.request_id; return true
 end
 local options={enabled=true,epoch=string.rep('a',32),nonce=string.rep('b',32),slot=name=='slot2' and 2 or 1,
  expected_save_path='/tmp/private/45841/save',timeout=10,guard=function() return active end,
  log=function(line) logs[#logs+1]=line;return true end}
 local module=dofile('tools/dev/authority_fixture_local_offset.lua')
 assert(not module.new({enabled=false}))
 local owner=assert(module.new(options));assert(not module.new(options))
 assert(owner:tick())
 local function respond(phase, actor)
  local value=options.nonce..phase..'|'..options.epoch..'|'..(options.slot+2)..'|'..(actor or '0x65')..'|0x66|0x67'
  events['X4AuthorityFixtureLocalOffset.Result'](nil,value)
 end
 if name=='guard' then active=false end
 if name=='refused' then events['X4AuthorityFixtureLocalOffset.Refused'](); assert(owner:state()=='failed' and writes==0); return end
 respond('1', name=='wrong_pre' and '0x68' or nil)
 if name=='player' or name=='docked' or name=='guard' or name=='wrong_pre' then
  assert(owner:state()=='failed' and writes==0, name);return
 end
 if name=='write_error' then assert(owner:state()=='failed' and writes==1);assert(not owner:tick() and writes==1);return end
 assert(owner:state()=='post_pending' and writes==1, name)
 assert(owner:tick() and #issued==2)
 respond('2',name=='wrong_identity' and '0x68' or nil)
 if name=='wrong_identity' then assert(owner:state()=='failed' and writes==1);return end
 assert(owner:state()=='done' and writes==1 and owner:result().after.x==110)
 assert(logs[1]:match('^WRITE_ENTERED ') and logs[2]:match('^OBSERVED '))
 assert(owner:tick() and writes==1)
end
for _,name in ipairs({'normal','slot2','player','docked','guard','refused','wrong_pre','write_error','wrong_identity'}) do scenario(name) end
