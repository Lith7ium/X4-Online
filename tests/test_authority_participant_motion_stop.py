"""Opt-in client STOP/STOPPED; real UDP and Lua, simulated X4 and MD."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC

@unittest.skipUnless(shutil.which('luajit') and shutil.which('cc') and os.name=='posix','LuaJIT and C compiler required')
class MotionStop(unittest.TestCase):
 def test_local_owner_contract(self):
  subprocess.run(['luajit','tests/authority_motion_client_stop.lua'],cwd=ROOT,check=True,capture_output=True,timeout=5)
 def run_udp(self,mode):
  with tempfile.TemporaryDirectory() as tmp:
   net=Path(tmp)/'net.so';abi=Path(tmp)/'abi.so'
   subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(net)],cwd=ROOT,check=True,capture_output=True)
   subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/replica_motion_binding_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
   sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
   env=dict(os.environ,LD_PRELOAD=str(abi),TEST_NET_LIB=str(net),TEST_NET_PORT=str(sock.getsockname()[1]),TEST_MOTION_STOP=mode)
   proc=subprocess.Popen(['luajit','tests/authority_saved_motion_pair_client_fake_x4.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   bridge=ExperimentalParticipantMotionIPC(sock,enabled=True,lease='a'*32,attempt='b'*32,epoch='c'*32,generation='d'*32,
     guard=lambda:proc.poll() is None,validate_peer=lambda p:p[0]=='127.0.0.1',timeout=.5,stop_enabled=True)
   try:
    self.assertTrue(bridge.wait_ready())
    value={'version':1,'epoch':'c'*32,'generation':'d'*32,'index':42,'sequence':1,'sector_macro':'sector_a',
      'source_time':1,'x':1,'y':2,'z':3,'velocity':None}
    self.assertTrue(bridge(value,False))
    if mode=='ok':
     self.assertTrue(bridge.stop_remote());self.assertEqual(bridge.state,'remote_stopped')
     # A packet after STOP must fault the stopped Lua owner; it cannot restart.
     sock.send(b'late');proc.wait(timeout=2);self.assertNotEqual(proc.returncode,0)
    else:
     with self.assertRaises((RuntimeError,TimeoutError)):bridge.stop_remote()
     self.assertEqual(bridge.state,'failed')
   finally:
    if bridge.state=='remote_stopped':bridge.close()
    sock.close()
    if proc.poll() is None:proc.terminate()
    proc.communicate(timeout=3)
 def test_stop_then_late_packet_faults(self):self.run_udp('ok')
 def test_refused_stop_never_confirms(self):self.run_udp('refuse')
 def test_close_before_confirmed_stop_fails(self):
  server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0))
  peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0))
  try:
   lease,attempt,epoch,generation='1'*32,'2'*32,'b'*32,'c'*32
   peer.sendto(f'R|{lease}|{attempt}|READY|{epoch}|{generation}'.encode(),server.getsockname())
   bridge=ExperimentalParticipantMotionIPC(server,enabled=True,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
      guard=lambda:True,validate_peer=lambda address:address==peer.getsockname(),timeout=1,stop_enabled=True)
   self.assertTrue(bridge.wait_ready())
   with self.assertRaisesRegex(RuntimeError,'cannot close'):bridge.close()
   self.assertEqual(bridge.state,'failed')
  finally:server.close();peer.close()
 def test_close_before_ready_is_not_a_confirmed_stop(self):
  server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0))
  try:
   bridge=ExperimentalParticipantMotionIPC(server,enabled=True,lease='1'*32,attempt='2'*32,epoch='b'*32,generation='c'*32,
      guard=lambda:True,validate_peer=lambda _:True,timeout=1,stop_enabled=True)
   with self.assertRaisesRegex(RuntimeError,'cannot close'):bridge.close()
   self.assertEqual(bridge.state,'failed')
   self.assertEqual(server.fileno(),-1)  # failure still relinquishes the owned raw FD
  finally:server.close()
 def test_foreign_stop_receipt_fails(self):
  server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0))
  peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0));peer.settimeout(2)
  try:
   lease,attempt,epoch,generation='1'*32,'2'*32,'b'*32,'c'*32
   peer.sendto(f'R|{lease}|{attempt}|READY|{epoch}|{generation}'.encode(),server.getsockname())
   bridge=ExperimentalParticipantMotionIPC(server,enabled=True,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
      guard=lambda:True,validate_peer=lambda address:address==peer.getsockname(),timeout=1,stop_enabled=True)
   self.assertTrue(bridge.wait_ready())
   def respond():
    data,address=peer.recvfrom(769);parts=data.decode().split('|');parts[4]='f'*32
    peer.sendto('|'.join(['R',lease,attempt,'STOPPED',*parts[4:]]).encode(),address)
   thread=threading.Thread(target=respond);thread.start()
   with self.assertRaisesRegex(ValueError,'foreign'):bridge.stop_remote()
   thread.join(2);self.assertFalse(thread.is_alive());self.assertEqual(bridge.state,'failed')
  finally:server.close();peer.close()

if __name__=='__main__':unittest.main()
