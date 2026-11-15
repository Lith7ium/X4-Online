"""Native Lua clock: process-shared Linux monotonic domain and failures."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('cc') and shutil.which('luajit'),
                     'Linux compiler and LuaJIT required')
class MonotonicClockTests(unittest.TestCase):
    def test_real_lua_clock_matches_python_monotonic(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'net.so'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
                            str(ROOT/'src/native/net.c'),'-ldl','-o',str(lib)],check=True,capture_output=True)
            script=r'''
local n=assert(package.loadlib(arg[1],'luaopen_x4lan_net'))()
local previous=assert(n.monotonic())
for i=1,100 do local now=assert(n.monotonic());assert(now>=previous);previous=now end
io.write(string.format('%.9f\n',previous))
'''
            start=time.monotonic()
            process=subprocess.run(['luajit','-',str(lib)],input=script,text=True,capture_output=True,check=True)
            end=time.monotonic()
            self.assertLessEqual(start,float(process.stdout.strip()))
            self.assertLessEqual(float(process.stdout.strip()),end)

    def test_native_failure_and_invalid_times_return_nil(self):
        source=r'''
#define clock_gettime test_clock_gettime
#include "NET_SOURCE"
#include <assert.h>
static int mode, was_nil, was_number;static double result;
int test_clock_gettime(clockid_t which, struct timespec *t) {
 assert(which==CLOCK_MONOTONIC);
 if(mode==1) return -1;
 t->tv_sec=mode==2 ? -1 : 3;
 t->tv_nsec=mode==3 ? -1 : (mode==4 ? 1000000000L : 250000000L);
 return 0;
}
static void push_nil(lua_State *L) {(void)L;was_nil++;}
static void push_number(lua_State *L,double n) {(void)L;was_number++;result=n;}
int main(void) {
 p_lua_pushnil=push_nil;p_lua_pushnumber=push_number;
 for(mode=1;mode<=4;mode++) {was_nil=was_number=0;assert(net_monotonic(0)==1);assert(was_nil==1 && !was_number);}
 mode=0;was_nil=was_number=0;assert(net_monotonic(0)==1);assert(!was_nil && was_number==1 && result==3.25);
 return 0;
}
'''.replace('NET_SOURCE',str(ROOT/'src/native/net.c'))
        with tempfile.TemporaryDirectory() as tmp:
            source_file=Path(tmp)/'clock.c';binary=Path(tmp)/'clock'
            source_file.write_text(source)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(source_file),'-ldl','-o',str(binary)],
                           check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)


if __name__=='__main__':
    unittest.main()
