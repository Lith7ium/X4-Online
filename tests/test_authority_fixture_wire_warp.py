"""Focused mocked checks: one network receipt must lead to one delayed write result."""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
from authority_fixture_wire_warp_support import validate


def event(s): return '[X4LAN] NATIVE_GATE ' + s


def evidence():
    identity = 'ship=' + 'a'*64 + ' sector=' + 'b'*64
    return ([event('AUTHORITY_APPLY_ENROLL ' + identity),
             event('AUTHORITY_WIRE_SOURCE tick=51 seq=5 x=20 y=1 z=2')],
            [event('AUTHORITY_APPLY_ENROLL ' + identity),
             event('AUTHORITY_WIRE_RECEIVE tick=52 request=4 seq=5 x=20 y=1 z=2'),
             event('AUTHORITY_APPLY_REQUEST request=4 seq=5 x=20 y=1 z=2 before_x=0 before_y=1 before_z=2'),
             event('AUTHORITY_APPLY_ACK'), event('AUTHORITY_APPLY_LATE elapsed=1.1 x=20 y=1 z=2')])


class EvidenceTest(unittest.TestCase):
    def test_matching_unique_received_sample_and_late_read(self):
        self.assertTrue(validate(*evidence())['pass'])

    def test_missing_receipt_wrong_identity_or_false_alignment_fail(self):
        source, guest = evidence()
        for replacement in (guest[:1] + guest[2:],
                            [guest[0].replace('b'*64, 'c'*64), *guest[1:]],
                            [*guest[:2], guest[2].replace('before_x=0', 'before_x=20'), *guest[3:]],
                            [*guest[:-1], guest[-1].replace('elapsed=1.1', 'elapsed=0.5')],
                            [*guest[:-1], guest[-1].replace('x=20', 'x=0')],
                            guest + [guest[2]]):
            self.assertFalse(validate(source, replacement)['pass'])
        self.assertFalse(validate(source + [source[-1]], guest)['pass'])
        self.assertFalse(validate([source[0], source[1].replace('tick=51', 'tick=39')], guest)['pass'])

    @unittest.skipUnless(shutil.which('luajit'), 'requires luajit')
    def test_configuration_failure_reports_only_fixed_stage(self):
        script = r'''
local m=assert(loadfile('src/authority/lua/fixture_wire_probe.lua'))()
local logs={}
m.sample({native_gate_authority_wire=true,native_gate_authority_wire_warp=true,test_profile='invalid'},30,{},function(s) logs[#logs+1]=s end,{})
assert(#logs==1 and logs[1]=='AUTHORITY_WIRE_ERROR tick=30 stage=configuration')
'''
        subprocess.run([shutil.which('luajit'), '-'], input=script, text=True, check=True, cwd=ROOT)

    @unittest.skipUnless(shutil.which('luajit'), 'requires luajit')
    def test_guest_wire_probe_forwards_only_received_position(self):
        script = r'''
local now=0;local actor=1;local position={x=0,y=0,z=0};local emitted={};local callback;local logs={}
local C={IsValidComponent=function() return true end,GetPlayerControlledShipID=function() return 4 end,
 GetPlayerOccupiedShipID=function() return 5 end,GetPlayerContainerID=function() return 6 end,
 GetContextByClass=function(obj,kind) if obj==1 then return kind=='zone' and 3 or 2 end
  if kind=='ship' then return 0 else return 7 end end}
package.loaded.ffi={C=C,cdef=function() end,new=function(_,v) return v end}
local wire={sent=0};function wire:step() self.sent=self.sent+1;return {request=1,source_sequence=1,x=20,y=2,z=3} end
X4LAN_AUTHORITY_FIXTURE_WIRE={new=function() return wire end}
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {key=function(v) return v==0 and '' or tostring(v) end,
 operational=function() return true end,is_ship=function() return true end,sector=function() return 2 end,
 pose=function() return position end} end}
X4LAN_SHA256={digest=function(s) return s end}
package.loadlib=function() return function() return {open=function() return {close=function() end} end,
 monotonic=function() return now end} end end
ConvertStringToLuaID=function(s) return s end
GetComponentData=function() return false,false,false end
RegisterEvent=function(_,f) callback=f end
AddUITriggeredEvent=function(_,_,v) emitted[#emitted+1]=v end
assert(loadfile('tools/dev/authority_fixture_wire_warp.lua'))()
local m=assert(loadfile('src/authority/lua/fixture_wire_probe.lua'))()
local cfg={native_gate_authority_wire=true,native_gate_authority_wire_warp=true,test_profile='45841',slot='p2',
 native_gate_authority_wire_port=9999,native_gate_authority_wire_lease=string.rep('a',32),
 native_gate_snapshot_fixture={string.rep('1',16),2,3,4,5,6,7,8,9,10,11,12},native_gate_authority_warp_sector=string.rep('2',16)}
local gate={saved_identity=function(v) return v=='1' and string.rep('1',16) or string.rep('2',16) end}
local function log(v) logs[#logs+1]=v end
m.sample(cfg,44,{actor},log,gate);assert(#emitted==0)
m.sample(cfg,45,{actor},log,gate);assert(#emitted==1 and emitted[1].x==20 and emitted[1].y==2)
m.sample(cfg,46,{actor},log,gate);assert(#emitted==1)
callback(nil,'applied');now=1.1;position={x=20,y=2,z=3};m.sample(cfg,47,{actor},log,gate)
assert(logs[#logs]:find('AUTHORITY_APPLY_LATE',1,true))
'''
        subprocess.run([shutil.which('luajit'), '-'], input=script, text=True, check=True, cwd=ROOT)

    @unittest.skipUnless(shutil.which('luajit'), 'requires luajit')
    def test_lua_state_machine_submits_exactly_once_and_waits_for_ack(self):
        script = r'''
local m=assert(loadfile('tools/dev/authority_fixture_wire_warp.lua'))()
local p={x=0,y=0,z=0};local t=0;local writes=0;local rows={}
local s=m.new({read=function() return p end,clock=function() return t end,
 log=function(x) rows[#rows+1]=x end,send=function(target) writes=writes+1;assert(target.x==20) end})
s:sample({x=1,y=0,z=0,request=1,source_sequence=1}); assert(writes==0)
s:sample({x=20,y=0,z=0,request=2,source_sequence=2}); assert(writes==1)
s:sample({x=30,y=0,z=0,request=3,source_sequence=3}); assert(writes==1)
assert(not pcall(function() s:ack('refused') end));s:ack('applied')
t=0.9;s:sample();assert(#rows==2)
t=1.1;p={x=20,y=0,z=0};s:sample();s:sample();assert(#rows==3 and writes==1)
assert(not pcall(function() s:ack('applied') end))
'''
        subprocess.run([shutil.which('luajit'), '-'], input=script, text=True, check=True, cwd=ROOT)
