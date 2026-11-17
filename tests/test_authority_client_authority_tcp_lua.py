"""One real TCP→UDP→Lua authority session; X4, MD, time and grant are fake."""
import json,os,socket,subprocess,tempfile,threading,time,unittest
from pathlib import Path
from tests import test_authority_experimental_tcp_motion as fixture
from tools.dev import authority_client_authority_bind as binder
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_client_authority_motion import ExperimentalTCPClientAuthorityMotion
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
ROOT=Path(__file__).resolve().parents[1]

class TCPToLua(unittest.TestCase):
 def test_pull_reaches_actual_lua_session(self):
  for include_orientation in (False,True):
   with self.subTest(include_orientation=include_orientation):
    self.check_lua_session(include_orientation)
 def check_lua_session(self,include_orientation):
  case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp()
  stop=threading.Event();errors=[];thread=proc=udp=None
  try:
   with tempfile.TemporaryDirectory() as tmp:
    lib=Path(tmp)/'net.so'
    subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(lib)],cwd=ROOT,check=True,capture_output=True)
    peer=case.case.connect();case.case.offer_and_claim(peer)
    udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0))
    env=dict(os.environ,TEST_NET_LIB=str(lib),TEST_NET_PORT=str(udp.getsockname()[1]),
             TEST_INCLUDE_ORIENTATION='1' if include_orientation else '0')
    proc=subprocess.Popen(['luajit','tests/authority_client_authority_motion_udp_fake_x4.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    st=os.stat(f'/proc/{proc.pid}/exe');fields=Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()
    identity={'pid':proc.pid,'start_ticks':int(fields[19]),'exe_dev':st.st_dev,'exe_ino':st.st_ino}
    grant={'session_epoch':'a'*32,'epoch':'b'*32,'generation':'c'*32,'index':1318,
           'sector_macro':'cluster_115_sector001_macro','token':'d'*32,'incarnation':'e'*32}
    def participant():
     bridge=None
     try:
      peer.settimeout(3);data=b''
      while not data.endswith(b'\n'):data+=peer.recv(1)
      assert json.loads(data)['kind']=='accepted'
      bridge=binder.bind_client_authority(udp,process=identity,lease='1'*32,attempt='2'*32,
       epoch=grant['epoch'],generation=grant['generation'],incarnation=grant['incarnation'],token=grant['token'],
       session_epoch=grant['session_epoch'],guard=lambda:proc.poll() is None,running=lambda:proc.poll() is None,
       grant=lambda e,g,n,t,i,s:(e,g,n,t,i,s)==(grant['epoch'],grant['generation'],grant['index'],grant['token'],grant['incarnation'],grant['session_epoch']),timeout=3,include_orientation=include_orientation)
      assert bridge.register_saved()
      app=ExperimentalTCPParticipantClient(peer,fixture.Controller(),enabled=True,epoch=grant['session_epoch'],handle=1,timeout=3,
       authority_grant=grant,authority_guard=lambda g:g==grant,pull_authority_motion=bridge.pull)
      while not stop.is_set():app.poll(.05)
      app.close();bridge.close()
     except BaseException as exc:
      if not stop.is_set():errors.append(exc)
    thread=threading.Thread(target=participant);thread.start();case.case.host.tick(.1)
    delivery=ExperimentalTCPJobDelivery(case.case.host,enabled=True,timeout=3);delivery.bind_test_incarnation(1,grant['incarnation'],enabled=True)
    owner=ExperimentalTCPClientAuthorityMotion(delivery,enabled=True,grant=grant,guard=lambda g:g==grant and proc.poll() is None)
    sample=owner.pull()
    self.assertIsNotNone(sample);self.assertEqual((sample['index'],sample['sequence'],sample['sector_macro'],sample['velocity']),
      (1318,1,grant['sector_macro'],None))
    self.assertEqual((sample['x'],sample['y'],sample['z']),(1.,2.,3.));self.assertFalse(case.case.host._failed)
    self.assertEqual(sample['version'],2 if include_orientation else 1)
    if include_orientation:
     self.assertEqual(sample['orientation'],{'yaw':.1,'pitch':.2,'roll':.3});self.assertIsNone(sample['angular_rate'])
    else:
     self.assertNotIn('orientation',sample);self.assertNotIn('angular_rate',sample)
    next_sample=None;deadline=time.monotonic()+2
    while next_sample is None and time.monotonic()<deadline:next_sample=owner.pull()
    self.assertIsNotNone(next_sample)
    self.assertEqual(next_sample['velocity'],{'x':0.,'y':0.,'z':0.})
    if include_orientation:self.assertEqual(next_sample['angular_rate'],{'yaw':0.,'pitch':0.,'roll':0.})
  finally:
   stop.set()
   if thread:thread.join(3)
   if proc:
    if proc.poll() is None:proc.terminate()
    _,stderr=proc.communicate(timeout=3)
    if stderr and proc.returncode not in (0,-15):errors.append(RuntimeError(stderr))
   if udp:udp.close()
   case.doCleanups()
  self.assertFalse(thread and thread.is_alive());self.assertEqual(errors,[])
if __name__=='__main__':unittest.main()
