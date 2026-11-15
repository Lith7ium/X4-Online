import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LUAJIT = shutil.which('luajit')

FIXTURE = r'''
local apply=assert(loadfile('src/authority/lua/pose_apply.lua'))()
local writes=0
local p={x=0,y=0,z=0,yaw=0,pitch=0,roll=0}
local e={
 isolated=function() return true end,
 operational=function() return true end,
 is_ship=function() return true end,
 controlled_ship=function() return 'player' end,
 occupied_ship=function() return false end,
 player_container=function() return false end,
 key=function(h) return h end,
 sector=function() return 'sector' end,
 dock_state=function() return false,false,false end,
 container=function() return false end,
 pose=function() return p end,
 set_pose=function(ship,sector,value)
  assert(ship=='fixture' and sector=='sector'); writes=writes+1
  p={x=value.x,y=value.y,z=value.z,yaw=value.yaw*math.pi/180,
     pitch=value.pitch*math.pi/180,roll=value.roll*math.pi/180}
 end,
}
local ids={ship=function() return 'test-only-fixture-1' end,sector=function() return 'sector-id' end}
local expected={enabled=true,fixture_id='test-only-fixture-1',sector_id='sector-id'}
local target={x=25,y=0,z=0,yaw=0,pitch=0,roll=0}
local function make() return apply.new(e,ids,'fixture','sector',expected) end
'''


@unittest.skipUnless(LUAJIT, 'LuaJIT is required')
class PoseApplyTests(unittest.TestCase):
    def run_lua(self, body):
        proc = subprocess.run([LUAJIT, '-'], input=FIXTURE + body, text=True,
                              cwd=ROOT, capture_output=True, env=os.environ.copy())
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_disabled_requires_explicit_fixture_and_no_calls_at_load(self):
        self.run_lua('''
expected.enabled=false
assert(not pcall(make)); assert(writes==0)
expected.enabled=true; expected.fixture_id='ordinary-ship'
assert(not pcall(make)); assert(writes==0)
''')

    def test_only_fixture_written_once_and_delayed_observation_detects_drift(self):
        self.run_lua('''
local experiment=make()
local no,pre=experiment.observe(); assert(not no and pre:find('confirmed write',1,true))
local result,err=experiment.attempt(target); assert(result,err and err.error)
assert(writes==1 and result.before.x==0 and result.immediate.x==25 and result.immediate_matches)
local wrong,why=experiment.observe({x=999}); assert(not wrong and why:find('takes no target',1,true))
result.target.x=99; target.x=88
local observed=assert(experiment.observe()); assert(observed.matches)
p.x=28
observed=assert(experiment.observe()); assert(not observed.matches)
local again,why=experiment.attempt(target); assert(not again and why.attempted_write==false and writes==1)
''')

    def test_safety_preconditions_refuse_before_any_setter(self):
        self.run_lua('''
local cases={
 function() e.isolated=function() return false end end,
 function() e.operational=function() return false end end,
 function() e.is_ship=function() return false end end,
 function() e.controlled_ship=function() return 'fixture' end end,
 function() e.controlled_ship=function() return nil end end,
 function() e.occupied_ship=function() return 'fixture' end end,
 function() e.occupied_ship=function() return nil end end,
 function() e.player_container=function() return 'fixture' end end,
 function() e.player_container=function() return nil end end,
 function() e.sector=function() return 'other' end end,
 function() e.dock_state=function() return true,false,false end end,
 function() e.dock_state=function() return false,true,false end end,
 function() e.dock_state=function() return false,false,true end end,
 function() e.dock_state=function() return nil,false,false end end,
 function() e.container=function() return 'station' end end,
 function() e.container=function() return nil end end,
 function() ids.ship=function() return 'other' end end,
 function() ids.sector=function() return 'other' end end,
}
local defaults={}; for k,v in pairs(e) do defaults[k]=v end
local default_ship,default_sector=ids.ship,ids.sector
for _,modify in ipairs(cases) do
 for k,v in pairs(defaults) do e[k]=v end; ids.ship,ids.sector=default_ship,default_sector
 modify(); local result,why=make().attempt(target)
 assert(not result and why.attempted_write==false and writes==0)
end
''')

    def test_bad_target_nonfinite_position_and_failed_readback(self):
        self.run_lua('''
local invalid={0,1,0/0,math.huge,51,10000001}
for _,x in ipairs(invalid) do
 local result,why=make().attempt({x=x,y=0,z=0,yaw=0,pitch=0,roll=0})
 assert(not result and why.attempted_write==false and writes==0)
end
e.set_pose=function() writes=writes+1 end
local experiment=make()
local result,why=experiment.attempt(target)
assert(not result and why.attempted_write==true and why.error:find('immediate readback mismatch',1,true))
local observed,reason=experiment.observe(); assert(not observed and reason:find('confirmed write',1,true) and writes==1)
''')

    def test_radians_are_written_as_degrees_and_read_back_in_radians(self):
        self.run_lua('''
target.yaw=math.pi/2; target.pitch=-math.pi/4; target.roll=math.pi/6
local setter=e.set_pose
e.set_pose=function(ship,sector,value)
 assert(math.abs(value.yaw-90)<1e-9 and math.abs(value.pitch+45)<1e-9 and math.abs(value.roll-30)<1e-9)
 setter(ship,sector,value)
end
local experiment=make()
local result=assert(experiment.attempt(target))
assert(math.abs(result.immediate.yaw-math.pi/2)<1e-9)
assert(math.abs(result.immediate.pitch+math.pi/4)<1e-9)
assert(math.abs(result.immediate.roll-math.pi/6)<1e-9)
assert(experiment.observe().matches)
''')

    def test_post_write_error_reported_as_indeterminate(self):
        self.run_lua('''
e.set_pose=function() writes=writes+1; error('setter failed') end
local experiment=make()
local result,why=experiment.attempt(target)
assert(not result and why.attempted_write==true and writes==1)
local observed,reason=experiment.observe()
assert(not observed and reason:find('confirmed write',1,true))
''')

    def test_identity_or_dock_changes_during_observation_fail_closed(self):
        self.run_lua('''
local experiment=make()
local result=assert(experiment.attempt(target)); assert(result.immediate_matches)
e.key=function(h) if h=='fixture' then return 'replaced-fixture' end return h end
local value,why=experiment.observe()
assert(not value and why:find('handle changed',1,true))
e.key=function(h) return h end
e.dock_state=function() return false,true,false end
value,why=experiment.observe()
assert(not value and why:find('not confirmed free',1,true) and writes==1)
''')


if __name__ == '__main__':
    unittest.main()
