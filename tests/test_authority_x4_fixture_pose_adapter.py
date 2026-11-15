"""Mocked X4 adapter safety contract; does not start or modify X4."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
LUAJIT=shutil.which('luajit')

FIXTURE=r'''
local apply=assert(loadfile('src/authority/lua/pose_apply.lua'))()
local adapter=assert(loadfile('src/authority/lua/x4_fixture_pose_adapter.lua'))()
local a='111';local sector='222';local zone='333';local station='444';local room='555'
local a_saved='0000000000000001';local s_saved='0000000000000002'
local saved={['111']=a_saved,['222']=s_saved}
local gate={saved_identity=function(k) return saved[k] end}
local p={x=0,y=0,z=0,yaw=0,pitch=0,roll=0}
local writes,attests,parents,clearances=0,0,0,0
local state={path='/private/run/45841/save',controlled=false,occupied=false,player=station,
 docked=false,docking=false,stored=false,valid=true,operational=true,fixture_zone=zone,
 fixture_sector=sector,fixture_container=nil,parent=true,clearance=true}
local api={
 normalize=function(v) return v end,
 key=function(v) if not v then return '' end;return v end,
 path=function() return state.path end,
 valid=function(v) if v==a then return state.valid end;return v==station or v==room end,
 operational=function(v) return state.operational end,
 is_ship=function(v) return v==a end,
 context=function(v,class,self)
  if v==a then
   if class=='zone' then return state.fixture_zone elseif class=='sector' then return state.fixture_sector
   elseif class=='container' then return state.fixture_container end
  elseif v==room then
   if class=='ship' then return state.room_ship elseif class=='station' then return state.room_station end
  elseif v==station and class=='station' then return station end
 end,
 controlled=function() return state.controlled end,occupied=function() return state.occupied end,
 player_container=function() return state.player end,
 dock_state=function() return state.docked,state.docking,state.stored end,
 pose=function() return {x=p.x,y=p.y,z=p.z,yaw=p.yaw,pitch=p.pitch,roll=p.roll} end,
 set_pose=function(v,s,target)
  assert(v==a and s==sector);writes=writes+1
  p={x=target.x,y=target.y,z=target.z,yaw=target.yaw*math.pi/180,
     pitch=target.pitch*math.pi/180,roll=target.roll*math.pi/180}
 end,
}
local cfg={test_profile='45841',slot='p2',native_gate_fixture_pose_experiment=true,
 native_gate_snapshot_sha=string.rep('e',64),native_gate_snapshot_fixture={}}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=string.format('%016x',i) end
local options={enabled=true,cfg=cfg,gate=gate,pose_apply=apply,test_api=api,actor=a,sector=sector,
 expected_save_path='/private/run/45841/save',expected_sector_saved=s_saved,expected_snapshot_sha=string.rep('e',64),
 attest_private_profile=function(path,sha) attests=attests+1;return path==state.path and sha==cfg.native_gate_snapshot_sha and state.attested~=false end,
 prove_direct_parent=function(ship,parent) parents=parents+1;return ship==a and parent==zone and state.parent end,
 prove_no_other_player=function(ship) return ship==a and state.other_player~=true end,
 prove_clearance=function(ship,parent,before,target)
  clearances=clearances+1;return ship==a and parent==sector and state.clearance end}
local function make() return adapter.new(options) end
local function target() return {x=25,y=0,z=0,yaw=math.pi/2,pitch=-math.pi/4,roll=math.pi/6} end
'''


@unittest.skipUnless(LUAJIT,'LuaJIT required')
class X4FixturePoseAdapterTests(unittest.TestCase):
    def run_lua(self,body):
        result=subprocess.run([LUAJIT,'-'],input=FIXTURE+body,text=True,cwd=ROOT,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_default_off_and_trusted_dependencies_required(self):
        self.run_lua('''
options.enabled=false;assert(not pcall(make));assert(writes==0)
options.enabled=true;cfg.native_gate_fixture_pose_experiment=false;assert(not pcall(make));assert(writes==0)
cfg.native_gate_fixture_pose_experiment=true;options.expected_snapshot_sha=string.rep('f',64);assert(not pcall(make));assert(writes==0)
options.expected_snapshot_sha=string.rep('e',64);options.prove_clearance=nil;assert(not pcall(make));assert(writes==0)
''')

    def test_one_guarded_setter_readback_and_angle_convention(self):
        self.run_lua('''
local result,why=make().attempt(target());assert(result,why and why.error)
assert(writes==1 and clearances==1 and attests>=3 and parents>=3)
assert(math.abs(result.immediate.yaw-math.pi/2)<1e-9)
assert(math.abs(result.immediate.pitch+math.pi/4)<1e-9)
assert(math.abs(result.immediate.roll-math.pi/6)<1e-9)
''')

    def test_known_or_unknown_unsafe_state_rejects_write(self):
        self.run_lua('''
local changes={
 function() state.controlled=a end,function() state.occupied=a end,function() state.player=nil end,
 function() state.player=a end,function() state.player=room;state.room_ship=a end,
 function() state.player=room;state.room_ship=nil;state.room_station=nil end,
 function() state.docked=true end,function() state.docking=true end,function() state.stored=true end,
 function() state.docking=nil end,function() state.fixture_container='other' end,
 function() state.fixture_zone='other' end,function() state.fixture_sector='other' end,
 function() state.parent=false end,function() state.clearance=false end,function() state.attested=false end,
 function() state.other_player=true end,
 function() state.path='/other/45841/save' end,function() state.valid=false end,
 function() saved['111']='0000000000000042' end,function() saved['222']='0000000000000042' end,
}
local defaults={};for k,v in pairs(state) do defaults[k]=v end
for _,change in ipairs(changes) do
 for k in pairs(state) do state[k]=nil end;for k,v in pairs(defaults) do state[k]=v end
 saved['111']=a_saved;saved['222']=s_saved;change()
 local ok,experiment=pcall(make)
 if ok then local result=experiment.attempt(target());assert(not result) end
 assert(writes==0)
end
''')

    def test_clearance_callback_cannot_race_dock_player_or_parent_guard(self):
        self.run_lua('''
for _,change in ipairs({function() state.docked=true end,function() state.controlled=a end,
                         function() state.parent=false end,function() saved['111']='0000000000000042' end}) do
 state.docked=false;state.controlled=false;state.parent=true;saved['111']=a_saved
 options.prove_clearance=function() change();return true end
 -- The outer guard conservatively marks the entire setter call attempted;
 -- our final fence proves the injected native setter itself was not invoked.
 local result,why=make().attempt(target());assert(not result and why.attempted_write)
 assert(writes==0)
end
''')

    def test_clearance_callback_cannot_change_the_write_target(self):
        self.run_lua('''
options.prove_clearance=function(ship,parent,before,proposed)
 before.x=99999;proposed.x=99999;proposed.yaw=99999;return true
end
local result,why=make().attempt(target());assert(result,why and why.error)
assert(writes==1 and result.immediate.x==25 and math.abs(result.immediate.yaw-math.pi/2)<1e-9)
''')

    def test_native_dock_query_uses_exact_lua_component_id(self):
        self.run_lua('''
local ffi=require('ffi')
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
local actor=ffi.new('UniverseID',0x12345678)*4294967296+0x87654321
local sec=ffi.new('UniverseID',222);local zn=ffi.new('UniverseID',333);local st=ffi.new('UniverseID',444)
local actor_decimal=(tostring(actor):gsub('ULL$',''))
assert(tonumber(actor_decimal)>2^53)
local calls, setter_calls = 0, 0
local native={
 GetSaveFolderPath=function() return state.path end,
 IsValidComponent=function(v) return v==actor or v==st end,
 IsComponentOperational=function(v) return v==actor end,
 IsComponentClass=function(v,class) return class=='ship' and v==actor end,
 GetContextByClass=function(v,class,self)
  if v==actor and class=='zone' then return zn end
  if v==actor and class=='sector' then return sec end
  if v==st and class=='station' then return st end
  return ffi.new('UniverseID',0)
 end,
 GetPlayerControlledShipID=function() return ffi.new('UniverseID',0) end,
 GetPlayerOccupiedShipID=function() return ffi.new('UniverseID',0) end,
 GetPlayerContainerID=function() return st end,
 GetObjectPositionInSector=function() return p end,
 SetObjectSectorPos=function(v,s,value)
  assert(v==actor and s==sec);setter_calls=setter_calls+1
  p={x=value.x,y=value.y,z=value.z,yaw=value.yaw*math.pi/180,pitch=value.pitch*math.pi/180,roll=value.roll*math.pi/180}
 end,
}
package.loaded.ffi=setmetatable({C=native,string=function(v) return v end},{__index=ffi})
ConvertStringToLuaID=function(...)
 assert(select('#',...)==1)
 local decimal=...;assert(type(decimal)=='string' and decimal==actor_decimal)
 return {component=decimal}
end
GetComponentData=function(id,docked,docking,stored)
 assert(type(id)=='table' and id.component==actor_decimal)
 assert(docked=='isdocked' and docking=='isdocking' and stored=='isinternallystored')
 calls=calls+1;return false,false,false
end
gate.saved_identity=function(id)
 if id==actor_decimal then return a_saved elseif id=='222' then return s_saved end
end
options.test_api=nil;options.actor=actor;options.sector=sec
options.prove_direct_parent=function(ship,parent) return ship==actor and parent==zn end
options.prove_no_other_player=function(ship) return ship==actor end
options.prove_clearance=function(ship,parent) return ship==actor and parent==sec end
local result,why=make().attempt({x=25,y=0,z=0,yaw=0,pitch=0,roll=0})
assert(result,why and why.error);assert(calls>=2 and setter_calls==1)
''')


if __name__=='__main__':
    unittest.main()
