"""Real admitted TCP -> real UDP -> real Lua binding with fake MD/X4 ABI."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
import test_authority_experimental_tcp_participants as fixture

class Controller:
 def pause(self,_):return True
 def resume(self,_):return True

class MotionTCPToLua(unittest.TestCase):
 def run_binding(self,two):
  case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation');case.setUp()
  stop=threading.Event();ready=threading.Event();errors=[];thread=None;proc=None;sock=None
  try:
   with tempfile.TemporaryDirectory() as tmp:
    net=Path(tmp)/'net.so';abi=Path(tmp)/'fake.so'
    subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(net)],cwd=ROOT,check=True,capture_output=True)
    subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/replica_motion_binding_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
    tcp=case.connect();case.offer_and_claim(tcp)
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
    env=dict(os.environ,LD_PRELOAD=str(abi),TEST_NET_LIB=str(net),TEST_NET_PORT=str(sock.getsockname()[1]),TEST_TWO_SAMPLES='1' if two else '0')
    proc=subprocess.Popen(['luajit','tests/authority_motion_client_ipc_fake_x4.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def participant():
     try:
      tcp.settimeout(3);frame=b''
      while not frame.endswith(b'\n'):
       chunk=tcp.recv(1)
       if not chunk:raise RuntimeError('missing admission')
       frame+=chunk
      assert json.loads(frame)['kind']=='accepted'
      bridge=ExperimentalParticipantMotionIPC(sock,enabled=True,lease='a'*32,attempt='b'*32,epoch='c'*32,generation='d'*32,
          guard=lambda:proc.poll() is None,validate_peer=lambda p:p[0]=='127.0.0.1',timeout=1)
      bridge.wait_ready();ready.set()
      app=ExperimentalTCPParticipantClient(tcp,Controller(),enabled=True,epoch='a'*32,handle=1,timeout=2,apply_motion=bridge)
      while not stop.is_set():app.poll(.05)
      app.close();bridge.close()
     except BaseException as e:
      if not stop.is_set():errors.append(e)
    thread=threading.Thread(target=participant);thread.start();case.host.tick(.1);self.assertTrue(ready.wait(3))
    delivery=ExperimentalTCPJobDelivery(case.host,enabled=True,timeout=2)
    motion=ExperimentalTCPMotion(delivery,enabled=True);motion.track('c'*32,'d'*32,42)
    event={'version':1,'epoch':'c'*32,'generation':'d'*32,'index':42,'sequence':1,'sector_macro':'sector_a',
           'source_time':1,'x':1,'y':2,'z':3,'velocity':None}
    before=time.monotonic();self.assertTrue(motion.send(event));self.assertGreaterEqual(time.monotonic()-before,.18)
    if two:
     second={**event,'sequence':2,'source_time':1.5,'x':2,'velocity':{'x':2,'y':0,'z':0}}
     time.sleep(.025)
     before=time.monotonic();self.assertTrue(motion.send(second));self.assertGreaterEqual(time.monotonic()-before,.18)
    self.assertIsNone(proc.poll())
  finally:
   stop.set()
   if thread:thread.join(3)
   if proc:
    if proc.poll() is None:proc.terminate()
    proc.communicate(timeout=3)
   if sock:sock.close()
   case.doCleanups()
  self.assertFalse(thread and thread.is_alive());self.assertEqual(errors,[])
 def test_tcp_receipt_waits_for_real_lua_owner_correlated_md_and_ffi(self):self.run_binding(False)
 def test_two_received_samples_push_unknown_then_verified_rate(self):self.run_binding(True)
if __name__=='__main__':unittest.main()
