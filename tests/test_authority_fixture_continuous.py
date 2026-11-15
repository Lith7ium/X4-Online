"""Focused synthetic checks: no X4 process or save is touched."""
from pathlib import Path
import shutil
import socket
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
sys.path.insert(0, str(ROOT / 'src'))
from authority.fixture_udp import FixtureUDP
from authority_fixture_continuous_support import validate
import linux_gate_live as live


class ContinuousTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'requires luajit')
    def test_rate_wire_and_repeated_writes(self):
        script = r'''
local wire=assert(loadfile('src/authority/lua/fixture_wire.lua'))()
local continuous=assert(loadfile('src/authority/lua/fixture_continuous.lua'))()
local function channel() local c={incoming={},out={}}
 function c:send(v) self.out[#self.out+1]=v;return true end
 function c:receive() return table.remove(self.incoming,1) end;return c end
local key=string.rep('a',32);local s=channel();local source=wire.new(s,'SOURCE',key,'fixture',true)
s.incoming={'FIX1|READY|SOURCE|fixture'};source:step({x=1,y=2,z=3,vx=5,vy=0,vz=0})
assert(s.out[#s.out]=='FIX1|PUT|'..key..'|fixture|1|1|2|3|5|0|0')
local g=channel();local guest=wire.new(g,'GUEST',key,'fixture',true)
g.incoming={'FIX1|READY|GUEST|fixture'};guest:step()
g.incoming={'FIX1|POS|fixture|1|1|1|2|3|5|0|0'};local a=guest:step()
assert(a and a.vx==5 and a.x==1)
g.incoming={'FIX1|POS|fixture|2|2|2|2|3|bad|0|0'};assert(guest:step()==nil)
g.incoming={'FIX1|POS|fixture|3|3|2|2|3'};assert(guest:step().vx==nil)
local pos={x=0,y=0,z=0};local writes=0;local logs={};local now=0
local c=continuous.new({clock=function() now=now+.1;return now end,
 read=function() return pos end,write=function(t) writes=writes+1;pos=t end,
 log=function(s) logs[#logs+1]=s end})
c:sample({source_sequence=1,x=1,y=2,z=3});assert(writes==0)
c:sample(a);assert(writes==1 and pos.x==1.5)
c:sample({source_sequence=2,x=2,y=2,z=3,vx=5,vy=0,vz=0});assert(writes==2 and pos.x==2.5)
c:sample(nil);assert(#logs==4 and logs[2]:match('OBSERVE'))
'''
        subprocess.run(['luajit', '-'], input=script, cwd=ROOT, text=True, check=True, capture_output=True)

    @unittest.skipUnless(shutil.which('luajit'), 'requires luajit')
    def test_probe_guards_and_source_only_stimulus(self):
        text = (ROOT/'tools/dev/native_gate_probe.lua').read_text()
        guard = re.search(r"assert\(cfg.native_gate_authority_continuous==nil.*?excludes wire warp'\)", text, re.S).group()
        condition = re.search(r"if (tick==40 .*?) then AddUITriggeredEvent\('X4LAN_NativeGate','AuthorityMoveFixture'", text).group(1)
        script = r"""
local guard=assert(loadstring('local cfg=...; '..GUARD))
local condition=assert(loadstring('local cfg,tick=...; return '..CONDITION))
local good={test_profile='45841',native_gate_authority_wire=true,native_gate_authority_motion=true,native_gate_authority_continuous=true,slot='p1'}
assert(pcall(guard,good) and condition(good,40))
good.slot='p2';assert(not condition(good,40))
for _,bad in ipairs({{native_gate_authority_continuous='true'}, {native_gate_authority_continuous=true},
 {native_gate_authority_continuous=true,test_profile='45841',native_gate_authority_wire=true,native_gate_authority_motion=true,native_gate_authority_wire_warp=true}}) do assert(not pcall(guard,bad)) end
local read={native_gate_authority_motion=true,slot='p2'};assert(condition(read,40))
local warp={native_gate_authority_motion=true,native_gate_authority_wire_warp=true,slot='p2'};assert(not condition(warp,40))
""".replace('GUARD', repr(guard)).replace('CONDITION', repr(condition))
        subprocess.run(['luajit', '-'], input=script, cwd=ROOT, text=True, check=True, capture_output=True)

    def test_loopback_adapter_forwards_source_rate(self):
        adapter = FixtureUDP(fixture='fixture', source_lease='a'*32,
                             guest_lease='b'*32, max_age_seconds=2)
        source = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        guest = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        source.settimeout(1); guest.settimeout(1)
        try:
            source.sendto(('FIX1|HELLO|SOURCE|'+'a'*32+'|fixture').encode(), adapter.address)
            guest.sendto(('FIX1|HELLO|GUEST|'+'b'*32+'|fixture').encode(), adapter.address)
            adapter.poll(); source.recv(512); guest.recv(512)
            source.sendto(('FIX1|PUT|'+'a'*32+'|fixture|1|1|2|3|4|5|6').encode(), adapter.address)
            adapter.poll()
            guest.sendto(('FIX1|GET|'+'b'*32+'|fixture|1').encode(), adapter.address)
            adapter.poll()
            self.assertEqual(guest.recv(512), b'FIX1|POS|fixture|1|1|1.0|2.0|3.0|4.0|5.0|6.0')
        finally:
            source.close(); guest.close(); adapter.close()

    def test_bundle_opt_in_is_sealed_and_requires_motion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ('extension/x4_lan_lab/ui/ship_scan.lua', 'extension/x4_lan_lab/ui/x4_ship_engine.lua',
                     'extension/x4_lan_lab/ui/fixture_scan_probe.lua', 'extension/x4_lan_lab/ui/fixture_wire.lua',
                     'extension/x4_lan_lab/ui/fixture_wire_probe.lua', 'extension/x4_lan_lab/ui/fixture_continuous.lua',
                     'extension/x4_lan_lab/native/x4lan_net.so', 'fixture_udp.py',
                     'authority_fixture_wire_support.py', 'authority_fixture_continuous_support.py')
            files = {}
            for name in names:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.touch(); files[name] = 'stub'
            config = root/'extension/x4_lan_lab/ui/config.lua'
            config.write_text('X4LAN_CONFIG.native_gate_authority_scan = true\n'
                              'X4LAN_CONFIG.native_gate_battle_engage = false\n'
                              'X4LAN_CONFIG.native_gate_authority_wire = true\n'
                              'X4LAN_CONFIG.native_gate_authority_motion = true\n'
                              'X4LAN_CONFIG.native_gate_authority_continuous = true\n'
                              "X4LAN_CONFIG.native_gate_authority_warp_sector = '1111111111111111'\n")
            manifest = {'authority_fixture_scan': True, 'authority_fixture_wire': True,
                        'authority_fixture_motion': True, 'authority_fixture_continuous': True,
                        'battle': True, 'ticks': 300, 'clients': 2, 'files': files}
            live.validate_authority_scan_bundle(root, manifest)
            for changed in ({'authority_fixture_continuous': False}, {'authority_fixture_motion': False},
                            {'ticks': 299}, {'authority_fixture_wire_warp': True}):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    live.validate_authority_scan_bundle(root, dict(manifest, **changed))
            config.write_text(config.read_text().replace('native_gate_authority_continuous = true',
                                                          'native_gate_authority_continuous = false'))
            with self.assertRaises(ValueError):
                live.validate_authority_scan_bundle(root, manifest)

    def test_readback_and_rate_evidence(self):
        enrollment = 'AUTHORITY_APPLY_ENROLL ship=' + 'a'*64 + ' sector=' + 'b'*64
        source, guest = [enrollment], [enrollment]
        for i in range(1, 11):
            source.append(f'AUTHORITY_CONTINUOUS_SOURCE seq={i} vx=10 vy=0 vz=0')
            x = i * 10
            source.append(f'AUTHORITY_WIRE_SOURCE tick={i+30} seq={i} x={x} y=0 z=0')
            guest.append(f'AUTHORITY_WIRE_RECEIVE tick={i+30} request={i} seq={i} x={x} y=0 z=0')
            guest.append(f'AUTHORITY_CONTINUOUS_WRITE seq={i} x={x} y=0 z=0 vx=10 vy=0 vz=0 target_x={x+1} target_y=0 target_z=0 before_x={x-10} before_y=0 before_z=0')
            guest.append(f'AUTHORITY_CONTINUOUS_OBSERVE seq={i} x={x+1} y=0 z=0')
        self.assertTrue(validate(iter(source), iter(guest))['pass'])
        self.assertFalse(validate(source, guest[:-1])['pass'])
        swapped = guest.copy()
        first_write = next(i for i, row in enumerate(swapped) if 'CONTINUOUS_WRITE seq=1 ' in row)
        swapped[first_write], swapped[first_write+1] = swapped[first_write+1], swapped[first_write]
        self.assertFalse(validate(source, swapped)['pass'])
        source.extend(['AUTHORITY_CONTINUOUS_SOURCE seq=11 vx=10 vy=0 vz=0',
                       'AUTHORITY_WIRE_SOURCE tick=41 seq=11 x=110 y=0 z=0'])
        guest.extend(['AUTHORITY_WIRE_RECEIVE tick=41 request=11 seq=11 x=110 y=0 z=0',
                      'AUTHORITY_CONTINUOUS_WRITE seq=11 x=110 y=0 z=0 vx=10 vy=0 vz=0 target_x=111 target_y=0 target_z=0 before_x=100 before_y=0 before_z=0'])
        unfinished=validate(source,guest)
        self.assertTrue(unfinished['pass']);self.assertEqual(unfinished['unobserved_final_write'],1)
        self.assertFalse(validate(source, [s.replace('OBSERVE seq=5 x=51', 'OBSERVE seq=5 x=0') for s in guest if 'OBSERVE' not in s or 'seq=5' not in s])['pass'])
        mismatch = source.copy(); mismatch[1] = mismatch[1].replace('vx=10', 'vx=20')
        self.assertFalse(validate(mismatch, guest)['pass'])
        stationary = [s if 'OBSERVE' not in s else s.split(' x=')[0]+' x=0 y=0 z=0' for s in guest]
        self.assertFalse(validate(source, stationary)['pass'])
