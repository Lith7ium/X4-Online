"""Real Lua/Python stop handshake and process-owned UDP; no X4."""
import os
from pathlib import Path
import select
import shutil
import sys
import socket
import subprocess
import tempfile
import unittest
from tests import test_authority_experimental_tcp_motion as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority_source_job_bind import bind_source
from authority_tcp_job_client_live import socket_owner

ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(sys.platform=='linux' and shutil.which('cc') and shutil.which('luajit'),
                     'Linux, C compiler and LuaJIT required')
class LuaStopIntegration(unittest.TestCase):
 def test_correlated_stop_reaches_lua_then_peer_remains_owned(self):
  case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp()
  proc=sock=None
  try:
   with tempfile.TemporaryDirectory() as tmp:
    library=Path(tmp)/'net.so'
    subprocess.run(['cc','-std=c11','-shared','-fPIC','src/native/net.c','-ldl','-o',str(library)],cwd=ROOT,check=True,capture_output=True)
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));destination=sock.getsockname()
    env=dict(os.environ,TEST_NET_LIB=str(library),TEST_NET_PORT=str(destination[1]))
    proc=subprocess.Popen(['luajit','tests/authority_source_motion_stop_udp.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    st=os.stat(f'/proc/{proc.pid}/exe');fields=Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()
    ident={'pid':proc.pid,'start_ticks':int(fields[19]),'exe_dev':st.st_dev,'exe_ino':st.st_ino}
    sock=bind_source(sock,process=ident,lease='1'*32,attempt='2'*32,epoch='b'*32,generation='c'*32,
                     guard=lambda:proc.poll() is None,timeout=3)
    delivery=ExperimentalTCPJobDelivery(case.case.host,enabled=True,timeout=.1)
    motion=ExperimentalTCPMotion(delivery,enabled=True)
    bridge=ExperimentalSourceMotionIPC(sock,motion,enabled=True,lease='1'*32,attempt='2'*32,epoch='b'*32,generation='c'*32,
        guard=lambda:proc.poll() is None,validate_peer=lambda peer:socket_owner(peer,destination,ident),timeout=2,stop_enabled=True)
    self.assertTrue(bridge.stop_remote())
    self.assertTrue(select.select([proc.stdout],[],[],2)[0]);self.assertEqual(proc.stdout.readline().strip(),'STOPPED')
    self.assertIsNone(proc.poll());self.assertTrue(socket_owner(sock.getpeername(),destination,ident))
    bridge.close();sock=None
  finally:
   try:
    if proc:
     if proc.poll() is None:proc.terminate()
     try:proc.communicate(timeout=3)
     except subprocess.TimeoutExpired:
      # The unreaped Popen child cannot have its PID reused here.
      proc.kill();proc.communicate(timeout=3)
   finally:
    try:
     if sock:sock.close()
    finally:case.doCleanups()

if __name__=='__main__':unittest.main()
