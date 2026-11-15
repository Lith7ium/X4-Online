"""Synthetic diagnostic only: loopback sockets, no X4 state or Internet."""
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority.fixture_fleet_udp import FixtureFleetUDP  # noqa: E402

FIXTURES = {'ship%02d' % i: 'frame%d' % (i % 3) for i in range(12)}
GUESTS = {'GUEST1': 'b' * 32, 'GUEST2': 'c' * 32}


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.adapter = FixtureFleetUDP(fixtures=FIXTURES, source_lease='a'*32,
                                       guests=GUESTS, max_age_seconds=1)
        self.addCleanup(self.adapter.close)
        self.source, self.guest1, self.guest2, self.foreign = [self.endpoint() for _ in range(4)]

    def endpoint(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', 0))
        sock.settimeout(2)
        self.addCleanup(sock.close)
        return sock

    def send(self, sock, message):
        sock.sendto(message if isinstance(message, bytes) else message.encode('ascii'), self.adapter.address)
        self.assertTrue(select.select([self.adapter.sock], [], [], 2)[0])
        self.assertEqual(self.adapter.poll(), 1)

    def hello(self, sock, role, lease):
        self.send(sock, f'FLEET1|HELLO|{role}|{lease}')
        self.assertEqual(sock.recv(512), f'FLEET1|READY|{role}'.encode())

    def empty(self, sock):
        self.assertFalse(select.select([sock], [], [], .005)[0])

    def put(self, sock, lease, fixture, frame, seq, xyz='1|2|3'):
        self.send(sock, f'FLEET1|PUT|{lease}|{fixture}|{frame}|{seq}|{xyz}')

    def get(self, sock, lease, fixture, frame, seq):
        self.send(sock, f'FLEET1|GET|{lease}|{fixture}|{frame}|{seq}')

    def test_frames_roles_per_fixture_sequences_and_guests(self):
        self.hello(self.source, 'SOURCE', 'a'*32)
        self.hello(self.guest1, 'GUEST1', 'b'*32)
        self.hello(self.guest2, 'GUEST2', 'c'*32)
        self.hello(self.guest1, 'GUEST1', 'b'*32)  # retry lost READY
        self.send(self.foreign, f'FLEET1|HELLO|SOURCE|{"a"*32}')
        self.send(self.source, f'FLEET1|HELLO|GUEST1|{"b"*32}')
        self.empty(self.foreign); self.empty(self.source)
        self.get(self.guest1, 'b'*32, 'ship00', 'frame0', 1)
        self.empty(self.guest1)  # missing source sample
        self.put(self.guest1, 'a'*32, 'ship00', 'frame0', 1)
        self.put(self.source, 'b'*32, 'ship00', 'frame0', 1)
        self.put(self.source, 'a'*32, 'ship00', 'wrong', 1)
        self.put(self.source, 'a'*32, 'unknown', 'frame0', 1)
        self.put(self.source, 'a'*32, 'ship00', 'frame0', 1, 'nan|2|3')
        self.get(self.guest1, 'b'*32, 'ship00', 'frame0', 2)
        self.empty(self.guest1)
        self.put(self.source, 'a'*32, 'ship00', 'frame0', 4, '1|2|3')
        self.put(self.source, 'a'*32, 'ship01', 'frame1', 1, '9|8|7')
        self.put(self.source, 'a'*32, 'ship00', 'frame0', 3, '999|999|999')
        self.put(self.source, 'a'*32, 'ship00', 'frame0', 4, '999|999|999')
        self.get(self.guest1, 'b'*32, 'ship00', 'wrong', 3)
        self.get(self.guest1, 'c'*32, 'ship00', 'frame0', 3)
        self.empty(self.guest1)
        self.get(self.guest1, 'b'*32, 'ship00', 'frame0', 3)
        self.assertEqual(self.guest1.recv(512), b'FLEET1|POS|ship00|frame0|3|4|1.0|2.0|3.0')
        self.get(self.guest2, 'c'*32, 'ship00', 'frame0', 1)
        self.assertEqual(self.guest2.recv(512), b'FLEET1|POS|ship00|frame0|1|4|1.0|2.0|3.0')
        self.get(self.guest1, 'b'*32, 'ship01', 'frame1', 1)
        self.assertEqual(self.guest1.recv(512), b'FLEET1|POS|ship01|frame1|1|1|9.0|8.0|7.0')
        self.get(self.guest1, 'b'*32, 'ship00', 'frame0', 3)
        self.empty(self.guest1)
        self.send(self.source, b'X'*513)
        self.send(self.source, b'\xff')

    def test_expired_data_and_duplicates_cannot_refresh_it(self):
        self.hello(self.source, 'SOURCE', 'a'*32)
        self.hello(self.guest1, 'GUEST1', 'b'*32)
        with patch('authority.fixture_fleet_udp.time.monotonic', return_value=10):
            self.put(self.source, 'a'*32, 'ship00', 'frame0', 1)
        with patch('authority.fixture_fleet_udp.time.monotonic', return_value=12):
            self.put(self.source, 'a'*32, 'ship00', 'frame0', 1, '9|9|9')
            self.get(self.guest1, 'b'*32, 'ship00', 'frame0', 1)
            self.empty(self.guest1)
            self.put(self.source, 'a'*32, 'ship00', 'frame0', 2, '4|5|6')
            self.get(self.guest1, 'b'*32, 'ship00', 'frame0', 2)
            self.assertEqual(self.guest1.recv(512), b'FLEET1|POS|ship00|frame0|2|2|4.0|5.0|6.0')

    def test_configuration_is_bounded_and_defensively_copied(self):
        fixtures = dict(FIXTURES)
        candidate = FixtureFleetUDP(fixtures=fixtures, source_lease='d'*32, guests={'GUEST1': 'e'*32}, max_age_seconds=1)
        self.addCleanup(candidate.close)
        fixtures['ship00'] = 'changed'
        self.assertEqual(candidate.fixtures['ship00'], 'frame0')
        defaults = dict(fixtures=FIXTURES, source_lease='a'*32, guests=GUESTS, max_age_seconds=1)
        for change in ({'fixtures': dict(list(FIXTURES.items())[:11])}, {'guests': {}},
                       {'guests': {'GUEST0': 'd'*32}}, {'guests': {'GUEST1': 'a'*32}},
                       {'max_age_seconds': float('nan')}, {'bind': ('0.0.0.0', 0)}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                FixtureFleetUDP(**(defaults | change))
        with self.assertRaises(ValueError):
            candidate.poll(65)


@unittest.skipUnless(shutil.which('luajit') and shutil.which('cc') and sys.platform.startswith('linux'),
                     'requires Linux compiler and LuaJIT')
class LuaFleetTests(unittest.TestCase):
    def test_guest_rejects_expired_unsolicited_wrong_frame_and_reordered_replies(self):
        script = r'''
local wire=assert(loadfile('src/authority/lua/fixture_fleet_wire.lua'))()
local c={incoming={},out={}}
function c:send(p) self.out[#self.out+1]=p;return true end
function c:receive() return table.remove(self.incoming,1) end
local fixtures={};for i=0,11 do fixtures[string.format('ship%02d',i)]='frame'..(i%3) end
local g=wire.new(c,'GUEST1',string.rep('b',32),fixtures,0.3)
g:step(nil,0)
c.incoming={'FLEET1|READY|GUEST1'};assert(#g:step(nil,0.1)==0)
c.incoming={'FLEET1|POS|ship00|wrong|1|1|1|2|3',
 'FLEET1|POS|ship00|frame0|99|1|1|2|3',
 'FLEET1|POS|ship00|frame0|1|1|nan|2|3'}
assert(#g:step(nil,0.2)==0)
c.incoming={'FLEET1|POS|ship00|frame0|1|1|1|2|3',
 'FLEET1|POS|ship00|frame0|2|1|1|2|3'}
assert(#g:step(nil,0.7)==0) -- both requests expired
c.incoming={'FLEET1|POS|ship00|frame0|3|5|7|8|9',
 'FLEET1|POS|ship00|frame0|3|5|99|99|99',
 'FLEET1|POS|ship00|frame0|2|4|99|99|99'}
local updates=g:step(nil,0.8);assert(#updates==1 and updates[1].x==7)
assert(not pcall(function() g:step(nil,0.5) end)) -- clock cannot go backwards
'''
        result = subprocess.run(['luajit', '-'], input=script, text=True, cwd=ROOT,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_native_udp_module_source_and_two_guests(self):
        """Separate Lua sockets exchange all 12 moving fixtures through Python."""
        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp) / 'x4lan_net.so'
            subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                            str(ROOT / 'src/native/net.c'), '-ldl', '-o', str(lib)], check=True, capture_output=True)
            adapter = FixtureFleetUDP(fixtures=FIXTURES, source_lease='a'*32, guests=GUESTS, max_age_seconds=5)
            done = threading.Event()
            def poll():
                while not done.wait(.0005):
                    adapter.poll()
            thread = threading.Thread(target=poll, daemon=True)
            thread.start()
            try:
                script = r'''
local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local net=assert(package.loadlib(LIB,'luaopen_x4lan_net'))()
local wire=assert(loadfile('src/authority/lua/fixture_fleet_wire.lua'))()
local fixtures={};for i=0,11 do fixtures[string.format('ship%02d',i)]='frame'..(i%3) end
local sc=net.open('127.0.0.1',PORT);local ac=net.open('127.0.0.1',PORT);local bc=net.open('127.0.0.1',PORT)
local s=wire.new(sc,'SOURCE',string.rep('a',32),fixtures)
local a=wire.new(ac,'GUEST1',string.rep('b',32),fixtures,0.5)
local b=wire.new(bc,'GUEST2',string.rep('c',32),fixtures,0.5)
local seen={{},{}};local finished=false
for turn=1,4000 do
 local samples={};for i=0,11 do samples[string.format('ship%02d',i)]={x=i*100+turn,y=i,z=-turn} end
 s:step(samples)
 local groups={a:step(nil,turn/1000),b:step(nil,turn/1000)}
 for g=1,2 do for _,u in ipairs(groups[g]) do
  local i=assert(tonumber(u.fixture:match('^ship(%d%d)$')))
  assert(u.frame=='frame'..(i%3) and u.y==i and u.x==i*100-u.z)
  seen[g][u.fixture]=(seen[g][u.fixture] or 0)+1
 end end
 finished=true
 for g=1,2 do for id in pairs(fixtures) do if (seen[g][id] or 0)<2 then finished=false end end end
 if finished then break end
 ffi.C.usleep(1000)
end
assert(finished,'both guests must receive multiple updates for all 12 fixtures')
sc:close();ac:close();bc:close()
'''.replace('LIB', repr(str(lib))).replace('PORT', str(adapter.address[1]))
                result = subprocess.run(['luajit', '-'], input=script, text=True, cwd=ROOT,
                                        capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                done.set(); thread.join(timeout=2); adapter.close()


if __name__ == '__main__':
    unittest.main()
