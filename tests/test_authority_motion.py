"""Pure Lua motion reconstruction, without game state or network transport."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LUAJIT = shutil.which('luajit')


@unittest.skipUnless(LUAJIT, 'requires LuaJIT')
class MotionTests(unittest.TestCase):
    def lua(self, code):
        script = "local M=assert(loadfile('src/authority/lua/motion_buffer.lua'))()\n" + code
        result = subprocess.run([LUAJIT, '-'], input=script, text=True, cwd=ROOT,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_three_dimensional_unrelated_clocks_hold_without_prediction(self):
        self.lua(r'''
local m=M.new({dimensions=3,hold_only=true})
local p={1,2,3};local v={10,0,-5}
assert(m:push({frame=string.rep('a',128),sequence=1,source_time=1000,pose=p,rate=v},4))
p[1]=900;v[1]=900
local r=m:render(5);assert(r.phase=='held-clock-unverified' and r.pose[1]==1 and #r.pose==3 and r.linear_velocity==nil)
assert(m:push({frame='other',sequence=2,source_time=2000,pose={8,9,10}},6))
r=m:render(100000);assert(r.phase=='held-clock-unverified' and r.pose[1]==8 and r.linear_velocity==nil)
assert(not m:push({frame='other',sequence=2,source_time=2001,pose={8,9,10}},100001))
local legacy=M.new();assert(not legacy:push({frame='A',sequence=1,source_time=1,pose={1,2,3}},2))
''')

    def test_irregular_samples_interpolate_then_extrapolate_then_freeze(self):
        self.lua(r'''
local m=M.new({delay=.15,horizon=.35,clock_leak=0})
local function add(seq,t,arrival,x)
 return m:push({frame='sector-A',sequence=seq,source_time=t,pose={x,0,0,0,0,0},rate={100,0,0,0,0,0}},arrival)
end
assert(add(1,1,10,0));assert(add(2,1.1,10.12,10));assert(add(3,1.3,10.32,30))
local a=m:render(10.32);assert(a.phase=='interpolated' and math.abs(a.pose[1]-17)<.00001)
local b=m:render(10.65);assert(b.phase=='extrapolated' and math.abs(b.pose[1]-50)<.00001)
local c=m:render(10.9);assert(c.phase=='frozen' and math.abs(c.pose[1]-65)<.00001)
local d=m:render(20);assert(d.phase=='frozen' and math.abs(d.pose[1]-65)<.00001)
''')

    def test_frame_transition_teleport_and_gap_clear_old_samples(self):
        self.lua(r'''
local m=M.new({delay=.05,horizon=.3,stale=.5,teleport_distance=25,clock_leak=0})
local function s(seq,t,f,x,rate) return {sequence=seq,source_time=t,frame=f,pose={x,0,0,0,0,0},rate=rate} end
local zero={0,0,0,0,0,0};local huge={100000,0,0,0,0,0}
assert(m:push(s(1,1,'A',0,zero),11))
local ok,reason=m:push(s(2,1.1,'A',100,huge),11.1)
assert(ok and reason=='teleport') -- incoming speed cannot excuse the jump
local p=m:render(11.1);assert(p.frame=='A' and p.pose[1]==100)
p=m:render(11.19);assert(p.pose[1]==100 and p.phase=='held-no-rate')
ok,reason=m:push(s(3,1.2,'B',-300,zero),11.2);assert(ok and reason=='frame')
p=m:render(11.2);assert(p.frame=='B' and p.pose[1]==-300)
ok,reason=m:push(s(4,2,'B',-290,zero),12);assert(ok and reason=='gap')
p=m:render(12);assert(p.frame=='B' and p.pose[1]==-290)
assert(not m:push(s(3,1.9,'A',0,zero),12.1))
''')

    def test_euler_wrap_estimated_rate_and_stationary_behavior(self):
        self.lua(r'''
local function s(seq,t,f,x,yaw) return {sequence=seq,source_time=t,frame=f,pose={x,0,0,yaw,0,0}} end
local a=s(1,10,'A',0,math.pi-.1)
local b=s(2,10.2,'A',20,-math.pi+.1)
local rate=M.estimate(a,b,.75)
assert(rate and math.abs(rate[1]-100)<1e-8 and math.abs(rate[4]-1)<1e-8)
assert(not M.estimate(a,s(2,10.2,'B',20,0),.75))
assert(not M.estimate(a,s(2,11,'A',0,0),.75))
local m=M.new({delay=.1,clock_leak=0});a.rate=rate;b.rate=rate
assert(m:push(a,20));assert(m:push(b,20.2))
local p=m:render(20.2)
assert(p.phase=='interpolated' and math.abs(math.abs(p.pose[4])-math.pi)<1e-8)
local q=m:render(20.35);assert(q.phase=='extrapolated' and math.abs(q.pose[4]-(-math.pi+.15))<1e-8)
local stationary=M.new({delay=0,horizon=.35,clock_leak=0})
local u=s(1,1,'A',9,0);local v=s(2,1.1,'A',9,0);v.rate=M.estimate(u,v,.75)
assert(v.rate and v.rate[1]==0 and v.rate[4]==0)
assert(stationary:push(u,2));assert(stationary:push(v,2.1))
local r=stationary:render(2.3);assert(r.pose[1]==9 and r.pose[4]==0)
r=stationary:render(4);assert(r.pose[1]==9 and r.phase=='frozen')
''')

    def test_missing_rate_invalid_values_reordering_and_copy(self):
        self.lua(r'''
local m=M.new({delay=0,clock_leak=0})
local pose={1,2,3,0,0,0};local s={frame='A',sequence=1,source_time=1,pose=pose}
assert(m:push(s,2));pose[1]=999;s.frame='B'
assert(select(2,m:render(1.9))=='invalid-clock')
local p=m:render(2.2);assert(p.pose[1]==1 and p.frame=='A' and p.phase=='held-no-rate')
local ok,reason=m:push({frame='A',sequence=2,source_time=1.1,pose={0/0,0,0,0,0,0}},2.3)
assert(not ok and reason=='invalid')
ok,reason=m:push({frame='A',sequence=1,source_time=1.2,pose={0,0,0,0,0,0}},2.4)
assert(not ok and reason=='stale')
ok,reason=m:push({frame='A',sequence=2,source_time=1.1,pose={0,0,0,0,0,0}},1.9)
assert(not ok and reason=='stale')
local value,err=m:render(2.1);assert(not value and err=='invalid-clock')
local bounded=M.new({delay=0,clock_leak=0})
assert(bounded:push({frame='A',sequence=1,source_time=1,pose={49999999,0,0,0,0,0},rate={1000,0,0,0,0,0}},2))
local out,why=bounded:render(2.1);assert(not out and why=='out-of-bounds')
assert(not pcall(function() M.new({horizon=-1}) end))
assert(not pcall(function() M.new({horizzon=.3}) end))
''')

    def test_rendered_linear_velocity_interpolation_prediction_and_freeze(self):
        self.lua(r'''
local m=M.new({delay=.15,horizon=.35,clock_leak=0})
local function add(seq,t,arrival,x,rate)
 return m:push({frame='A',sequence=seq,source_time=t,pose={x,0,0,0,0,0},rate=rate},arrival)
end
local rate={100,0,0,0,0,0}
assert(add(1,1,10,0,rate));assert(add(2,1.1,10.12,10,rate));assert(add(3,1.3,10.32,30,rate))
local first=m:render(10.32);assert(first.phase=='interpolated' and first.linear_velocity==nil)
local a=m:render(10.34);assert(a.phase=='interpolated' and math.abs(a.linear_velocity[1]-100)<1e-7)
local b=m:render(10.65);assert(b.phase=='extrapolated' and math.abs(b.linear_velocity[1]-100)<1e-7)
local c=m:render(10.9);assert(c.phase=='frozen' and c.linear_velocity[1]==0 and c.linear_velocity[2]==0)
local d=m:render(10.9);assert(d.phase=='frozen' and d.linear_velocity==nil)
''')

    def test_unknown_rate_frame_change_and_invalid_clock_stay_unknown(self):
        self.lua(r'''
local m=M.new({delay=0,clock_leak=0})
local function s(n,t,f,x,rate) return {sequence=n,source_time=t,frame=f,pose={x,0,0,0,0,0},rate=rate} end
assert(m:push(s(1,1,'A',1,nil),2))
assert(m:render(2.2).linear_velocity==nil)
assert(m:render(2.3).phase=='held-no-rate' and m:render(2.3).linear_velocity==nil)
local bad,why=m:render(2.2);assert(not bad and why=='invalid-clock')
local ok,reason=m:push(s(2,1.4,'B',2,{20,0,0,0,0,0}),2.4)
assert(ok and reason=='frame')
local after=m:render(2.5);assert(after.frame=='B' and after.linear_velocity==nil)
-- No transmitted rate is needed to infer a slope between two known poses.
local j=M.new({delay=.1,clock_leak=0})
assert(j:push(s(1,1,'A',0,nil),2));assert(j:push(s(2,1.2,'A',20,nil),2.2))
assert(j:render(2.2).linear_velocity==nil)
local k=j:render(2.25);assert(k.phase=='interpolated' and math.abs(k.linear_velocity[1]-100)<1e-6)
''')

    def test_rendered_rate_tracks_clock_slew_and_refuses_excessive_rate(self):
        self.lua(r'''
local m=M.new({delay=.2,clock_leak=.5,slew=.5,stale=1})
local function s(n,t,x) return {sequence=n,source_time=t,frame='A',pose={x,0,0,0,0,0},rate={100,0,0,0,0,0}} end
assert(m:push(s(1,1,0),10));assert(m:push(s(2,1.1,10),10.4))
assert(m:render(10.4));assert(m:render(10.5))
assert(m:push(s(3,1.2,20),10.6))
local slow=m:render(10.6);assert(slow.phase=='interpolated' and math.abs(slow.linear_velocity[1]-50)<1e-6)
assert(m:push(s(4,1.55,55),10.7))
local fast=m:render(10.7);assert(fast.phase=='interpolated' and math.abs(fast.linear_velocity[1]-150)<1e-6)
-- A large offset jump snaps the model clock; never report a derivative there.
assert(m:push(s(5,3,200),10.8))
assert(m:render(10.8).linear_velocity==nil)
local too=M.new({delay=.05,clock_leak=0})
assert(too:push(s(1,1,0),2));assert(too:push(s(2,1.000001,1),2.000001))
assert(too:render(2.000001))
local q=too:render(2.0500005);assert(q.phase=='interpolated' and q.linear_velocity==nil)
''')


if __name__ == '__main__':
    unittest.main()
