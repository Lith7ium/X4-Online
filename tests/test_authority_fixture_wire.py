"""Lua protocol tests; no X4, game writes or Internet service."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
LUAJIT = shutil.which('luajit')
CC = shutil.which('cc')
sys.path.insert(0, str(ROOT / 'src'))
from authority.fixture_udp import FixtureUDP  # noqa: E402


@unittest.skipUnless(LUAJIT, 'requires LuaJIT')
class FixtureWireTests(unittest.TestCase):
    def run_lua(self, body):
        subprocess.run([LUAJIT, '-'], input=body, text=True, cwd=ROOT, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_handshake_source_and_guest_filter_reordered_replies(self):
        self.run_lua(r'''
local wire=assert(loadfile('src/authority/lua/fixture_wire.lua'))()
local function channel()
 local t={out={},incoming={}}
 function t:send(v) self.out[#self.out+1]=v; return true end
 function t:receive() if #self.incoming==0 then return nil end; return table.remove(self.incoming,1) end
 return t
end
local key=string.rep('a',32)
local out=channel();local source=wire.new(out,'SOURCE',key,'fixture-1')
source:step();source:step()
assert(#out.out==2 and out.out[1]==out.out[2] and out.out[1]=='FIX1|HELLO|SOURCE|'..key..'|fixture-1')
out.incoming={'FIX1|READY|SOURCE|fixture-1'}
source:step({x=1,y=2,z=-3})
assert(out.out[#out.out]=='FIX1|PUT|'..key..'|fixture-1|1|1|2|-3')
local c=channel(); local guest=wire.new(c,'GUEST',key,'fixture-1')
guest:step()
c.incoming={'FIX1|READY|GUEST|fixture-1'};guest:step()
assert(c.out[#c.out]=='FIX1|GET|'..key..'|fixture-1|1')
c.incoming={'FIX1|POS|wrong|1|1|1|2|3','FIX1|POS|fixture-1|9|1|1|2|3',
            'FIX1|POS|fixture-1|1|1|1|2|3'}
local r=guest:step();assert(r and r.source_sequence==1 and r.x==1 and r.z==3)
c.incoming={'FIX1|POS|fixture-1|2|1|9|9|9','FIX1|POS|fixture-1|1|2|9|9|9',
            'FIX1|POS|fixture-1|2|2|4|5|6'}
r=guest:step();assert(r and r.source_sequence==2 and r.x==4)
''')

    def test_nonfinite_and_invalid_configuration_fail_closed(self):
        self.run_lua(r'''
local wire=assert(loadfile('src/authority/lua/fixture_wire.lua'))()
local c={incoming={}}
function c:send(v) return true end
function c:receive() return table.remove(self.incoming,1) end
local key=string.rep('a',32)
assert(not pcall(wire.new,c,'SOURCE','bad','fixture'))
assert(not pcall(wire.new,c,'OTHER',key,'fixture'))
local s=wire.new(c,'SOURCE',key,'fixture')
c.incoming={'FIX1|READY|SOURCE|fixture'}
assert(not pcall(function() s:step({x=0/0,y=0,z=0}) end))
''')

    @unittest.skipUnless(CC and sys.platform.startswith('linux'), 'requires Linux C compiler')
    def test_real_native_lua_udp_module_transfers_fixture(self):
        """Exercise the production native socket module, Lua codec and UDP adapter."""
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / 'x4lan_net.so'
            subprocess.run([CC, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-shared', '-fPIC', str(ROOT/'src/native/net.c'), '-ldl',
                            '-o', str(library)], check=True, capture_output=True)
            adapter = FixtureUDP(fixture='fixture-1', source_lease='a'*32,
                                 guest_lease='b'*32, max_age_seconds=2)
            done = threading.Event()
            def poll():
                while not done.wait(.001):
                    adapter.poll()
            thread = threading.Thread(target=poll, daemon=True)
            thread.start()
            try:
                script = r'''
local ffi=require('ffi'); ffi.cdef[[int usleep(unsigned int);]]
local net=assert(package.loadlib(LIBRARY, 'luaopen_x4lan_net'))()
local wire=assert(loadfile('src/authority/lua/fixture_wire.lua'))()
local source=net.open('127.0.0.1',PORT); local guest=net.open('127.0.0.1',PORT)
local s=wire.new(source,'SOURCE',string.rep('a',32),'fixture-1')
local g=wire.new(guest,'GUEST',string.rep('b',32),'fixture-1')
local received
for i=1,2000 do
 s:step({x=123.5,y=-20,z=7}); received=g:step()
 if received then break end
 ffi.C.usleep(1000)
end
assert(received and received.x==123.5 and received.y==-20 and received.z==7)
source:close();guest:close()
'''.replace('LIBRARY', json.dumps(str(library))).replace('PORT', str(adapter.address[1]))
                result = subprocess.run([LUAJIT, '-'], input=script, text=True, cwd=ROOT,
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                done.set()
                thread.join(timeout=2)
                adapter.close()


if __name__=='__main__':
    unittest.main()
