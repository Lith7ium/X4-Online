"""Real UDP readiness including zero/oversize packets; no X4."""
import os
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(sys.platform=='linux' and shutil.which('cc') and shutil.which('luajit'),'Linux, compiler and LuaJIT required')
class NetPendingTests(unittest.TestCase):
 def test_pending_detects_all_datagram_lengths_and_closed_socket(self):
  proc=None;sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  try:
   with tempfile.TemporaryDirectory() as tmp:
    lib=Path(tmp)/'net.so'
    subprocess.run(['cc','-std=c11','-shared','-fPIC','src/native/net.c','-ldl','-o',str(lib)],cwd=ROOT,check=True,capture_output=True)
    sock.bind(('127.0.0.1',0));sock.settimeout(3)
    env=dict(os.environ,TEST_NET_LIB=str(lib),TEST_NET_PORT=str(sock.getsockname()[1]))
    proc=subprocess.Popen(['luajit','tests/authority_net_pending.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    data,peer=sock.recvfrom(32);self.assertEqual(data,b'READY');sock.connect(peer)
    for index,payload in enumerate((b'',b'x'*1000,b'late'),1):
     sock.send(payload);self.assertTrue(select.select([proc.stdout],[],[],3)[0])
     self.assertEqual(proc.stdout.readline().strip(),'GOT '+str(index))
    self.assertEqual(proc.wait(timeout=3),0)
  finally:
   try:
    if proc:
     if proc.poll() is None:proc.terminate()
     try:proc.communicate(timeout=3)
     except subprocess.TimeoutExpired:proc.kill();proc.communicate(timeout=3)
   finally:sock.close()
if __name__=='__main__':unittest.main()
