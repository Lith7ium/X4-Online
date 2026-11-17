-- Fake native ABI only: repeated XYZ writes preserve actual orientation.
local ffi=require('ffi')
ffi.cdef[[int TestWrites(void);float TestYaw(void);void TestDrift(float);void TestPause(bool);int TestReads(void);]]
local setter=dofile('src/authority/lua/saved_motion_apply.lua')
local playback=dofile('src/authority/lua/motion_playback.lua')
local buffer=dofile('src/authority/lua/motion_buffer.lua')
local resolver=dofile('tools/dev/authority_registry_resolve_string.lua')
local now=1
function GetCurRealTime()return now end
function ConvertStringToLuaID(value)return ffi.new('uint64_t',tonumber(value))end
function ConvertIDTo64Bit(value)return value end
function GetComponentData(reference,...)
 local arguments={...}
 if arguments[1]=='isdocked' then return false,false,false end
 if arguments[1]=='macro' and tonumber(reference)==41 then return 'ship_ter_m_corvette_01_a_macro','pioneers' end
 if arguments[1]=='macro' and tonumber(reference)==43 then return 'cluster_115_sector001_macro' end
 error('unexpected component')
end
local options={enabled=true,test_profile='45841',expected_save_path='/private/45841/save',
 resolve=resolver,guard=function()return true end,playback=playback,buffer=buffer,max_age=2,max_step=50,
 binding={epoch=('b'):rep(32),index=1318,sector_macro='cluster_115_sector001_macro',actor_key='41',sector_key='43',zone_key='45'},
 record=function(event)
  assert(event.index==1318 and event.epoch==('b'):rep(32) and event.sector_macro=='cluster_115_sector001_macro')
  assert(event.actor_key==nil and event.sector_key==nil and event.zone_key==nil)
  return true
 end,fault=function(reason)error(reason)end}
local controller=assert(setter.new_playback_x4(options))
local function sample(sequence,x)
 return {frame='cluster_115_sector001_macro',sequence=sequence,source_time=20000+sequence,pose={x,0,0}}
end
assert(controller:push(sample(1,10),1) and controller:tick() and ffi.C.TestWrites()==1)
ffi.C.TestDrift(4);now=1.1
assert(controller:tick() and ffi.C.TestWrites()==2 and math.abs(ffi.C.TestYaw()-90)<.001)
local reads=ffi.C.TestReads();ffi.C.TestPause(true);now=1.2
assert(controller:tick() and ffi.C.TestReads()==reads and ffi.C.TestWrites()==2)
ffi.C.TestPause(false);now=1.3;assert(controller:tick() and ffi.C.TestWrites()==2)
now=1.31
assert(controller:push(sample(2,20),1.31) and controller:tick() and ffi.C.TestWrites()==3)
assert(math.abs(ffi.C.TestYaw()-90)<.001)
assert(controller:stop());now=1.4;assert(controller:tick() and ffi.C.TestWrites()==3)
-- The playback factory preserves enrolment checks previously enforced by one-shot begin.
for _,change in ipairs({{index=1},{epoch='invalid'},{sector_macro='other'},
 {actor_key='0'},{sector_key='invalid'},{zone_key='00'}}) do
 local invalid={};for key,value in pairs(options)do invalid[key]=value end
 invalid.binding={};for key,value in pairs(options.binding)do invalid.binding[key]=value end
 for key,value in pairs(change)do invalid.binding[key]=value end
 assert(not pcall(setter.new_playback_x4,invalid) and ffi.C.TestWrites()==3)
end
print('fake X4 playback factory preserves orientation and pause/read guards')
