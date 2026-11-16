"""Fake owners and native UDP on loopback; never starts X4."""
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
class ReplicaUDP(unittest.TestCase):
 def test_fake_owner_guards_and_order(self):
  subprocess.run(['luajit','tests/authority_census_replica_udp.lua'],cwd=ROOT,check=True,capture_output=True,timeout=5)
 @unittest.skipUnless(shutil.which('cc'),'compiler required')
 def test_full_fake_x4_binding(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'fake.so';subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_paused_job_descriptor_fake_x4.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
   subprocess.run(['luajit','tests/authority_census_replica_udp_fake_x4.lua',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=5)
 @unittest.skipUnless(shutil.which('cc'),'compiler required')
 def test_native_module_real_loopback(self):
  with tempfile.TemporaryDirectory() as tmp, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
   lib=Path(tmp)/'net.so';subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
   sock.bind(('127.0.0.1',0));sock.settimeout(3)
   proc=subprocess.Popen(['luajit','tests/authority_census_replica_udp_real.lua',str(lib),str(sock.getsockname()[1])],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   try:
    ready,peer=sock.recvfrom(768);self.assertTrue(ready.endswith(b'|READY'))
    prefix='|'.join(('CMD','a'*32,'client','b'*32,'c'*32))
    sock.sendto((prefix+'|WITNESS|2|41|sector_a').encode(),peer)
    msg,source=sock.recvfrom(768);self.assertEqual(source,peer);self.assertTrue(msg.endswith(b'|WITNESS_READY|2|41|sector_a'))
    sock.sendto((prefix+'|REPLICA|2|10055|ship_a|argon|sector_a|1|2|3').encode(),peer)
    msg,source=sock.recvfrom(768);self.assertEqual(source,peer);self.assertTrue(msg.endswith(b'|WITNESS_OK|2|41|sector_a'))
    sock.sendto((prefix+'|CHECK|1').encode(),peer);msg,source=sock.recvfrom(768);self.assertEqual(source,peer);self.assertTrue(msg.endswith(b'|CHECKED|1'))
   finally:
    if proc.poll() is None:proc.terminate()
    proc.communicate(timeout=3)
