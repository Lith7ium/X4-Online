"""Isolated fixture-wire harness tests; no X4 process or game mutation."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
from authority_fixture_wire_support import validate


class FixtureWireEvidenceTests(unittest.TestCase):
    def test_collector_never_exports_uncleaned_wire_credentials(self):
        import linux_gate_live as live
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp); case = run/'case1'; profile = case/'home/profile'
            profile.mkdir(parents=True)
            (profile/'engine-output.log').write_text('[X4LAN] NATIVE_GATE harmless\n')
            config = case/'extensions/x4_lan_lab/ui/config.lua'
            config.parent.mkdir(parents=True)
            secret = 'a'*32
            config.write_text('X4LAN_CONFIG.native_gate_authority_wire = true\n'
                              'X4LAN_CONFIG.native_gate_authority_wire_port = 12345\n'
                              f'X4LAN_CONFIG.native_gate_authority_wire_lease = "{secret}"\n'
                              'X4LAN_CONFIG.native_gate_authority_fleet_port = 12346\n'
                              f'X4LAN_CONFIG.native_gate_authority_fleet_lease = "{secret}"\n')
            with mock.patch.object(live, 'validate_evidence', return_value={}):
                live.collect_run_evidence(run, [1], [(case, profile)], 60,
                                          {'stride': 1, 'authority_fixture_wire': True}, True)
            exported = run/'client1/installed/x4_lan_lab-config.lua'
            self.assertNotIn(secret, exported.read_text())
            self.assertNotIn('native_gate_authority_wire_port', exported.read_text())
            self.assertNotIn('native_gate_authority_fleet_port', exported.read_text())
            self.assertIn('native_gate_authority_wire = true', exported.read_text())
            # A partial or otherwise unexpected assignment must remove any stale
            # export and refuse collection, not copy the untrusted remainder.
            config.write_text('X4LAN_CONFIG.native_gate_authority_wire_lease =\n"'+secret+'"\n')
            with self.assertRaisesRegex(ValueError, 'safely redact'):
                live.collect_run_evidence(run, [1], [(case, profile)], 60,
                                          {'stride': 1, 'authority_fixture_wire': True}, True)
            self.assertFalse(exported.exists())

    def test_matches_source_sequence_and_position_only(self):
        source = ['[X4LAN] NATIVE_GATE AUTHORITY_WIRE_SOURCE tick=30 seq=1 x=1.5 y=-2 z=3']
        guest = ['[X4LAN] NATIVE_GATE AUTHORITY_WIRE_RECEIVE tick=32 request=2 seq=1 x=1.5 y=-2 z=3']
        self.assertTrue(validate(source, guest, 60)['pass'])
        for bad in ([], [guest[0].replace('z=3', 'z=4')], guest * 2,
                    [guest[0].replace('seq=1', 'seq=2')],
                    ['[X4LAN] NATIVE_GATE AUTHORITY_WIRE_ERROR tick=31']):
            self.assertFalse(validate(source, bad, 60)['pass'])
        self.assertFalse(validate(source, guest, 31)['pass'])

    def test_motion_requires_matching_received_post_stimulus_positions(self):
        source = [
            '[X4LAN] NATIVE_GATE AUTHORITY_WIRE_SOURCE tick=39 seq=1 x=0 y=0 z=0',
            '[X4LAN] NATIVE_GATE AUTHORITY_WIRE_SOURCE tick=40 seq=2 x=0 y=0 z=0',
            '[X4LAN] NATIVE_GATE AUTHORITY_WIRE_SOURCE tick=50 seq=3 x=6 y=8 z=0',
        ]
        guest = [
            '[X4LAN] NATIVE_GATE AUTHORITY_WIRE_RECEIVE tick=41 request=1 seq=1 x=0 y=0 z=0',
            '[X4LAN] NATIVE_GATE AUTHORITY_WIRE_RECEIVE tick=42 request=2 seq=2 x=0 y=0 z=0',
            '[X4LAN] NATIVE_GATE AUTHORITY_WIRE_RECEIVE tick=52 request=3 seq=3 x=6 y=8 z=0',
        ]
        evidence = validate(source, guest, 120, require_motion=True)
        self.assertTrue(evidence['pass'])
        self.assertEqual(evidence['received_motion_m'], 10)
        self.assertFalse(validate(source, guest[:2], 120, require_motion=True)['pass'])
        self.assertFalse(validate(source, guest[1:2], 120, require_motion=True)['pass'])
        self.assertFalse(validate(source, [guest[0], guest[2]], 120, require_motion=True)['pass'])
        self.assertFalse(validate(source, guest[:-1] + [guest[-1].replace('x=6', 'x=7')], 120, require_motion=True)['pass'])
        below_source = source[:-1] + [source[-1].replace('y=8', 'y=7')]
        below_guest = guest[:-1] + [guest[-1].replace('y=8', 'y=7')]
        self.assertFalse(validate(below_source, below_guest, 120, require_motion=True)['pass'])

    def test_daemon_private_pipe_loopback_transfer_and_reap(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        directory = Path(scratch.name)
        shutil.copy(ROOT/'tools/dev/authority_fixture_wire_support.py', directory/'authority_fixture_wire_support.py')
        shutil.copy(ROOT/'src/authority/fixture_udp.py', directory/'fixture_udp.py')
        read_fd, write_fd = os.pipe()
        proc = subprocess.Popen([sys.executable, str(directory/'authority_fixture_wire_support.py'),
                                 '--config-fd', str(read_fd)], pass_fds=(read_fd,),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        os.close(read_fd)
        source_secret, guest_secret = 'a'*32, 'b'*32
        try:
            with os.fdopen(write_fd, 'w') as channel:
                json.dump({'source': source_secret, 'guest': guest_secret}, channel)
            ready = proc.stdout.readline()
            match = re.fullmatch(r'AUTHORITY_WIRE_READY port=(\d+)\n', ready)
            self.assertIsNotNone(match)
            address = ('127.0.0.1', int(match.group(1)))
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as source, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as guest:
                source.settimeout(2); guest.settimeout(2)
                for sock, role, lease in ((source, 'SOURCE', source_secret), (guest, 'GUEST', guest_secret)):
                    sock.sendto(f'FIX1|HELLO|{role}|{lease}|test-only-fixture-1'.encode(), address)
                    self.assertIn(b'FIX1|READY|', sock.recv(512))
                source.sendto(f'FIX1|PUT|{source_secret}|test-only-fixture-1|1|1|2|3'.encode(), address)
                # Datagram processing is sequential on this local socket; retry GET if the PUT
                # arrived after the first GET, using a fresh request sequence each time.
                received = None
                for number in range(1, 5):
                    guest.sendto(f'FIX1|GET|{guest_secret}|test-only-fixture-1|{number}'.encode(), address)
                    try:
                        received = guest.recv(512); break
                    except socket.timeout:
                        pass
                self.assertIsNotNone(received)
                self.assertIn(b'|1|1.0|2.0|3.0', received)
        finally:
            proc.send_signal(signal.SIGTERM)
            out, err = proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0)
        for secret in (source_secret, guest_secret):
            self.assertNotIn(secret, ready + out + err)

    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_probe_runs_every_tick_and_never_writes_game(self):
        script = r'''
local calls, logs = 0, {}
local sent={}
local transport={send=function(self,s) sent[#sent+1]=s;return true end, receive=function() return nil end,
 close=function() end}
package.loadlib=function() return function() return {open=function(host,port)
 assert(host=='127.0.0.1' and port==1234);return transport end} end end
package.loaded.ffi={new=function(_,v) return v end}
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {
 operational=function(h) assert(h==123);return true end,
 is_ship=function(h) return true end, sector=function(h) return 'sector' end,
 key=function(h) return h end,
 pose=function(h) calls=calls+1; return {x=1.5,y=-2,z=3} end,
} end}
X4LAN_AUTHORITY_FIXTURE_WIRE={new=function(conn,role,lease,fixture)
 assert(role=='SOURCE' and #lease==32 and fixture=='test-only-fixture-1')
 return {sent=0, step=function(self,p) self.sent=self.sent+1 end}
end}
local probe=assert(loadfile('src/authority/lua/fixture_wire_probe.lua'))()
local cfg={native_gate_authority_wire=true,native_gate_authority_wire_port=1234,
 native_gate_authority_wire_lease=string.rep('a',32),slot='p1',test_profile='45841'}
local function log(s) logs[#logs+1]=s end
probe.sample(cfg,29,{123},log);probe.sample(cfg,30,{123},log);probe.sample(cfg,31,{123},log)
assert(calls==2 and #logs==2 and logs[1]:find('AUTHORITY_WIRE_SOURCE tick=30 seq=1',1,true))
assert(not logs[1]:find(string.rep('a',32),1,true))
'''
        result = subprocess.run([shutil.which('luajit'), '-'], input=script, text=True,
                                cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_probe_rejects_sector_change_across_ticks(self):
        script = r'''
local logs, current_sector = {}, 'first'
local transport={send=function() return true end,receive=function() end,close=function() end}
package.loadlib=function() return function() return {open=function() return transport end} end end
package.loaded.ffi={new=function(_,v) return v end}
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {
 operational=function() return true end, is_ship=function() return true end,
 sector=function() return current_sector end, key=function(h) return h end,
 pose=function() return {x=1,y=2,z=3} end,
} end}
X4LAN_AUTHORITY_FIXTURE_WIRE={new=function()
 return {sent=0,step=function(self) self.sent=self.sent+1 end}
end}
local probe=assert(loadfile('src/authority/lua/fixture_wire_probe.lua'))()
local cfg={native_gate_authority_wire=true,native_gate_authority_wire_port=1234,
 native_gate_authority_wire_lease=string.rep('a',32),slot='p1',test_profile='45841'}
local function log(s) logs[#logs+1]=s end
probe.sample(cfg,30,{123},log)
current_sector='other'
probe.sample(cfg,31,{123},log)
assert(#logs==2 and logs[2]=='AUTHORITY_WIRE_ERROR tick=31')
'''
        result = subprocess.run([shutil.which('luajit'), '-'], input=script, text=True,
                                cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
