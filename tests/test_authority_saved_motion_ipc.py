"""Correlated saved registration over real local UDP; X4 peer is simulated."""
import socket, threading, unittest
from tests import test_authority_experimental_tcp_motion as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority.experimental_source_job_bridge import ExperimentalSourceJobBridge
from authority.experimental_job_motion_scheduler import ExperimentalJobMotionScheduler

class SavedMotion(unittest.TestCase):
 def setup_bridge(self,mode='ok',saved=True,on_pull=None):
  case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp();self.addCleanup(case.doCleanups)
  peer=case.case.connect();case.case.offer_and_claim(peer);case.client(peer,1);case.case.host.tick(.1)
  delivery=ExperimentalTCPJobDelivery(case.case.host,enabled=True,timeout=.5)
  motion=ExperimentalTCPMotion(delivery,enabled=True,min_interval=1/240)
  a=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);a.bind(('127.0.0.1',0));self.addCleanup(a.close)
  b=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);b.bind(('127.0.0.1',0));self.addCleanup(b.close)
  a.connect(b.getsockname());b.connect(a.getsockname());state={'guard':True};received=[]
  def source():
   b.settimeout(1)
   try:
    p=b.recv(769).decode().split('|');received.append(p)
    if mode=='timeout':return
    response=['S','1'*32,'2'*32,'SAVED_REGISTERED','b'*32,'c'*32,p[6],p[7],p[8]]
    if mode=='wrong_index':response[7]='43'
    if mode=='wrong_request':response[6]='9'
    if mode=='wrong_baseline':response[8]='99'
    if mode=='wrong_epoch':response[4]='0'*32
    if mode=='guard_loss':state['guard']=False
    b.send('|'.join(response).encode())
    if mode=='ok':
     p=b.recv(769).decode().split('|');received.append(p)
     if on_pull:on_pull()
     b.send('|'.join(['S','1'*32,'2'*32,'NO_SAMPLE','b'*32,'c'*32,p[6]]).encode())
   except (OSError,TimeoutError):return
  thread=threading.Thread(target=source);thread.start();self.addCleanup(thread.join,2)
  opts={'saved_baseline':100,'saved_guard':lambda e,n:state['guard'] and e=='b'*32 and n==100} if saved else {}
  bridge=ExperimentalSourceMotionIPC(a,motion,enabled=True,lease='1'*32,attempt='2'*32,epoch='b'*32,generation='c'*32,
   guard=lambda:True,validate_peer=lambda p:p==b.getsockname(),timeout=.7,**opts)
  return case,bridge,motion,received
 def test_correlated_registration_and_shared_request_counter(self):
  case,bridge,motion,received=self.setup_bridge()
  self.assertTrue(bridge.register_saved(42));self.assertIn(('b'*32,'c'*32,42),motion._tracks)
  self.assertIsNone(bridge.pull());self.assertEqual([(p[3],p[6]) for p in received],[('REGISTER_SAVED','1'),('PULL','2')]);bridge.close()
 def test_invalid_correlations_or_lost_guard_never_register_track(self):
  for mode in ('wrong_index','wrong_request','wrong_baseline','wrong_epoch','guard_loss','timeout'):
   with self.subTest(mode=mode):
    case,bridge,motion,_=self.setup_bridge(mode)
    with self.assertRaises((ValueError,RuntimeError,TimeoutError)):bridge.register_saved(42)
    self.assertNotIn(('b'*32,'c'*32,42),motion._tracks);self.assertTrue(case.case.host._failed)
 def test_disabled_or_out_of_range_fails_before_dispatch(self):
  for saved,index in ((False,42),(True,101)):
   with self.subTest(saved=saved,index=index):
    _,bridge,motion,received=self.setup_bridge('timeout',saved)
    with self.assertRaises(RuntimeError):bridge.register_saved(index)
    self.assertNotIn(('b'*32,'c'*32,index),motion._tracks);self.assertEqual(received,[])
 def test_duplicate_registration_fences(self):
  _,bridge,motion,_=self.setup_bridge()
  self.assertTrue(bridge.register_saved(42))
  with self.assertRaises(RuntimeError):bridge.register_saved(42)
 def test_job_registration_cannot_authorize_saved_apply(self):
  case,bridge,motion,_=self.setup_bridge('timeout')
  self.assertTrue(bridge.bind_confirmed(10055))
  with self.assertRaises(ValueError):bridge.apply_once(fixture.MotionTCP.sample())
  self.assertTrue(case.case.host._failed)
 def make_scheduler(self,bridge,motion):
  a=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);a.bind(('127.0.0.1',0));self.addCleanup(a.close)
  b=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);b.bind(('127.0.0.1',0));self.addCleanup(b.close)
  a.connect(b.getsockname());b.connect(a.getsockname())
  job=ExperimentalSourceJobBridge(motion._delivery,a,enabled=True,lease='7'*32,attempt='8'*32,
      epoch='b'*32,generation='c'*32,guard=lambda:True,timeout=1)
  scheduler=ExperimentalJobMotionScheduler(job,bridge,enabled=True);scheduler._test_peer=b;return scheduler
 def test_scheduler_owns_saved_registration(self):
  _,bridge,motion,_=self.setup_bridge()
  scheduler=self.make_scheduler(bridge,motion)
  self.assertTrue(scheduler.register_saved(42));self.assertEqual(scheduler.state,'ready')
  self.assertIsNone(scheduler.step()[1]);scheduler.close()
 def test_direct_registration_is_fenced_when_scheduler_owns_bridge(self):
  case,bridge,motion,received=self.setup_bridge('timeout')
  self.make_scheduler(bridge,motion)
  with self.assertRaises(RuntimeError):bridge.register_saved(42)
  self.assertEqual(received,[]);self.assertTrue(case.case.host._failed)
 def test_swallowed_reentrant_scheduler_call_fences_without_dispatch(self):
  case,bridge,motion,received=self.setup_bridge('timeout')
  scheduler=self.make_scheduler(bridge,motion)
  def attack(epoch,baseline):
   try:scheduler.register_saved(43)
   except RuntimeError:pass
   return True
  bridge._saved_guard=attack
  with self.assertRaises((RuntimeError,OSError)):scheduler.register_saved(42)
  self.assertEqual(received,[]);self.assertEqual(scheduler.state,'failed');self.assertTrue(case.case.host._failed)
 def test_saved_guard_cannot_poll_shared_control_reader(self):
  case,bridge,_,_=self.setup_bridge();blocked=[]
  def attack(epoch,baseline):
   try:case.case.host._control.poll(0)
   except RuntimeError:blocked.append(True)
   return True
  bridge._saved_guard=attack
  self.assertTrue(bridge.register_saved(42));self.assertTrue(blocked)
  self.assertFalse(case.case.host._failed);bridge.close()
 def test_saved_registration_refuses_already_queued_source_job(self):
  case,bridge,motion,received=self.setup_bridge('timeout');scheduler=self.make_scheduler(bridge,motion)
  scheduler._test_peer.send(b'unexpected job')
  with self.assertRaises(RuntimeError):scheduler.register_saved(42)
  self.assertEqual(received,[]);self.assertEqual(scheduler.state,'failed');self.assertTrue(case.case.host._failed)
 def test_motion_only_fences_job_arriving_during_pull(self):
  ref={};case,bridge,motion,_=self.setup_bridge(on_pull=lambda:ref['scheduler']._test_peer.send(b'unexpected job'))
  scheduler=self.make_scheduler(bridge,motion);ref['scheduler']=scheduler
  self.assertTrue(scheduler.register_saved(42))
  with self.assertRaises(RuntimeError):scheduler.step_motion_only()
  self.assertEqual(scheduler.state,'failed');self.assertTrue(case.case.host._failed)

if __name__=='__main__':unittest.main()
