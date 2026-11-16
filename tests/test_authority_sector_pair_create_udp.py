"""Nonblocking Lua glue with fake X4 owners and real local UDP sockets."""
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
class PairUDP(unittest.TestCase):
 def test_fake_owner_failures_and_order(self):
  subprocess.run(['luajit','tests/authority_sector_pair_create_udp.lua'],cwd=ROOT,check=True,capture_output=True,timeout=5)
 @unittest.skipUnless(shutil.which('cc'),'compiler required')
 def test_real_loopback_udp_fake_owners(self):
  with tempfile.TemporaryDirectory() as tmp, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
   so=Path(tmp)/'net.so';subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(so)],cwd=ROOT,check=True,capture_output=True,timeout=10)
   sock.bind(('127.0.0.1',0));sock.settimeout(3)
   procs=[subprocess.Popen(['luajit','tests/authority_sector_pair_create_real_udp.lua',str(so),str(sock.getsockname()[1]),role],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for role in ('server','client')]
   peers={};prefix={};desc=None;awaiting=False;inspected=False;finished=False;checked=set()
   try:
    deadline=time.monotonic()+4
    while time.monotonic()<deadline and not (finished and checked=={'server','client'}):
     data,addr=sock.recvfrom(768);parts=data.decode('ascii').split('|')
     self.assertEqual(parts[0],'PAIR');role=parts[2];self.assertIn(role,('server','client'))
     self.assertEqual(parts[1],'a'*32 if role=='server' else 'd'*32);self.assertEqual(parts[3:5],['b'*32,'c'*32])
     self.assertTrue(role not in peers or peers[role]==addr);peers[role]=addr
     prefix[role]='|'.join(('CMD',parts[1],role,parts[3],parts[4]))
     event=parts[5]
     if event=='READY':sock.sendto((prefix[role]+'|START').encode(),addr)
     elif event=='AWAIT':awaiting=True
     elif event=='DESCRIPTOR':desc='|'.join(parts[6:])
     elif event=='INSPECTED':
      inspected=True;sock.sendto((prefix['server']+'|ACK|1|3').encode(),peers['server'])
      sock.sendto((prefix['client']+'|CHECK|1').encode(),peers['client'])
     elif event=='FINISHED':
      self.assertTrue(inspected);finished=True;sock.sendto((prefix['server']+'|CHECK|1').encode(),peers['server'])
     elif event=='CHECKED':self.assertEqual(parts[6],'1');checked.add(role)
     else:self.fail('unexpected event '+event)
     if desc is not None and awaiting:
      sock.sendto((prefix['client']+'|DESCRIPTOR|'+desc).encode(),peers['client']);desc=None;awaiting=False
    self.assertTrue(finished);self.assertEqual(checked,{'server','client'})
   finally:
    for p in procs:
     if p.poll() is None:p.terminate()
     p.communicate(timeout=3)
