"""Real Lua source/session and Python bridge over UDP; X4 ABI/MD simulated."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT/'tools/dev')]
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from authority_source_job_bind import bind_source
from authority_tcp_job_client_live import socket_owner
import test_authority_experimental_tcp_participants as fixture

class Controller:
 def pause(self,_): return True
 def resume(self,_): return True

class SavedUDPIntegration(unittest.TestCase):
 def test_saved_registration_then_sample_without_job_ack(self):
  case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation');case.setUp()
  stop=threading.Event();ready=threading.Event();errors=[];seen=[];proc=thread=sock=None
  try:
   with tempfile.TemporaryDirectory() as d:
    net,abi=Path(d)/'net.so',Path(d)/'abi.so'
    subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(net)],cwd=ROOT,check=True,capture_output=True)
    subprocess.run(['cc','-shared','-fPIC','-O2','tests/fixtures/multi_create_running_owner_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
    tcp=case.connect();case.offer_and_claim(tcp)
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
    env=dict(os.environ,LD_PRELOAD=str(abi),TEST_NET_LIB=str(net),TEST_NET_PORT=str(sock.getsockname()[1]))
    proc=subprocess.Popen(['luajit','tests/authority_source_saved_udp_fake_x4.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    st=os.stat(f'/proc/{proc.pid}/exe');fields=Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()
    ident={'pid':proc.pid,'start_ticks':int(fields[19]),'exe_dev':st.st_dev,'exe_ino':st.st_ino}
    def participant():
     try:
      tcp.settimeout(3);data=b''
      while not data.endswith(b'\n'):data+=tcp.recv(1)
      assert json.loads(data)['kind']=='accepted'
      adapter=ExperimentalTCPParticipantClient(tcp,Controller(),enabled=True,epoch='a'*32,handle=1,timeout=2,apply_motion=lambda value,despawn:seen.append(value) or True)
      ready.set()
      while not stop.is_set():adapter.poll(.05)
      adapter.close()
     except BaseException as exc:
      if not stop.is_set():errors.append(exc)
    thread=threading.Thread(target=participant);thread.start();case.host.tick(.1);self.assertTrue(ready.wait(3))
    sock=bind_source(sock,process=ident,lease='1'*32,attempt='2'*32,epoch='a'*32,generation='b'*32,guard=lambda:proc.poll() is None,timeout=3)
    destination=sock.getsockname();delivery=ExperimentalTCPJobDelivery(case.host,enabled=True,timeout=2)
    motion=ExperimentalTCPMotion(delivery,enabled=True)
    bridge=ExperimentalSourceMotionIPC(sock,motion,enabled=True,lease='1'*32,attempt='2'*32,epoch='a'*32,generation='b'*32,
      guard=lambda:proc.poll() is None,validate_peer=lambda peer:socket_owner(peer,destination,ident),timeout=3,
      saved_baseline=10054,saved_guard=lambda epoch,baseline:epoch=='a'*32 and baseline==10054)
    self.assertTrue(bridge.register_saved(42))
    result=bridge.pull();self.assertEqual((result['index'],result['sequence'],result['velocity']),(42,1,None))
    self.assertEqual(seen,[result]);bridge.close();sock=None
  finally:
   stop.set()
   if thread:thread.join(3)
   if proc:
    if proc.poll() is None:proc.terminate()
    proc.communicate(timeout=3)
   if sock:sock.close()
   case.doCleanups()
  self.assertFalse(thread and thread.is_alive());self.assertEqual(errors,[])

if __name__=='__main__':unittest.main()
