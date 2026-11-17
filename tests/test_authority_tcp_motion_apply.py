"""One-shot TCP apply uses the admitted socket and exact previously bound sample."""
import json,socket,threading,time,unittest
from tests import test_authority_experimental_tcp_motion as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient

class OneShot(unittest.TestCase):
 def setup_pair(self,*,allow=True,callback=None,preflight='READY'):
  case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp();self.addCleanup(case.doCleanups)
  peer=case.case.connect();case.case.offer_and_claim(peer);stop=threading.Event();received=[];errors=[]
  def client():
   try:
    peer.settimeout(2);raw=b''
    while not raw.endswith(b'\n'):raw+=peer.recv(1)
    assert json.loads(raw)['kind']=='accepted'
    app=ExperimentalTCPParticipantClient(peer,fixture.Controller(),enabled=True,epoch='a'*32,handle=1,timeout=1,
      apply_motion=lambda sample,despawn:True,apply_motion_once=callback or (lambda sample:received.append(sample) is None),
      preflight_motion=lambda sample:preflight)
    while not stop.is_set():app.poll(.05)
    app.close()
   except BaseException as error:
    if not stop.is_set():errors.append(error)
  thread=threading.Thread(target=client);thread.start()
  def cleanup():stop.set();thread.join(2);self.assertFalse(thread.is_alive())
  self.addCleanup(cleanup)
  case.case.host.tick(.1)
  delivery=ExperimentalTCPJobDelivery(case.case.host,enabled=True,timeout=1)
  motion=ExperimentalTCPMotion(delivery,enabled=True,allow_apply=allow);motion.track('b'*32,'c'*32,10055)
  return case,motion,received,errors
 def test_one_confirmed_sample_then_single_apply(self):
  case,motion,received,_=self.setup_pair();sample=fixture.MotionTCP.sample()
  self.assertTrue(motion.send(sample));self.assertEqual(motion.preflight(sample),'ready');self.assertTrue(motion.apply_once(sample));self.assertEqual(received,[sample])
  with self.assertRaises(RuntimeError):motion.apply_once(sample)
  self.assertTrue(case.case.host._failed)
 def test_changed_or_unconfirmed_sample_refused_before_apply(self):
  case,motion,received,_=self.setup_pair();sample=fixture.MotionTCP.sample();self.assertTrue(motion.send(sample));self.assertEqual(motion.preflight(sample),'ready')
  with self.assertRaises(ValueError):motion.apply_once({**sample,'x':9})
  self.assertEqual(received,[]);self.assertTrue(case.case.host._failed)
 def test_default_off_and_failed_readback_fence(self):
  for allow,callback in ((False,None),(True,lambda sample:False)):
   with self.subTest(allow=allow):
    case,motion,received,_=self.setup_pair(allow=allow,callback=callback);sample=fixture.MotionTCP.sample()
    self.assertTrue(motion.send(sample))
    if allow:self.assertEqual(motion.preflight(sample),'ready')
    with self.assertRaises((RuntimeError,ConnectionError,OSError,ValueError)):motion.apply_once(sample)
    self.assertTrue(case.case.host._failed)
 def test_near_never_authorizes_apply(self):
  case,motion,received,_=self.setup_pair(preflight='NEAR');sample=fixture.MotionTCP.sample()
  self.assertTrue(motion.send(sample));self.assertEqual(motion.preflight(sample),'near')
  with self.assertRaises(ValueError):motion.apply_once(sample)
  self.assertEqual(received,[]);self.assertTrue(case.case.host._failed)
 def test_new_sample_invalidates_ready_for_previous_sample(self):
  case,motion,received,_=self.setup_pair();sample=fixture.MotionTCP.sample()
  self.assertTrue(motion.send(sample));self.assertEqual(motion.preflight(sample),'ready');time.sleep(.02)
  self.assertTrue(motion.send(fixture.MotionTCP.sample(seq=2,t=2)))
  with self.assertRaises(ValueError):motion.apply_once(sample)
  self.assertEqual(received,[]);self.assertTrue(case.case.host._failed)
 def test_full_pose_apply_and_preflight_are_rejected_on_both_sides(self):
  sample={**fixture.MotionTCP.sample(),'version':2,
   'orientation':{'yaw':.1,'pitch':.2,'roll':.3},'angular_rate':None}
  for operation in ('preflight','apply_once'):
   with self.subTest(side='host',operation=operation):
    _,motion,received,_=self.setup_pair();self.assertTrue(motion.send(sample))
    with self.assertRaisesRegex(ValueError,'full-pose motion'):
     getattr(motion,operation)(sample)
    self.assertEqual(received,[])
  called=[]
  for operation in ('_motion_apply','_motion_preflight_command'):
   with self.subTest(side='participant',operation=operation):
    participant=object.__new__(ExperimentalTCPParticipantClient)
    participant._apply_motion_once=lambda _:called.append('apply')
    participant._preflight_motion=lambda _:called.append('preflight')
    participant._motion_write_attempted=False;participant._motion_preflight=None
    participant._handle=1;participant._epoch='session';participant._motion_incarnation='a'*32
    command={'version':1,'kind':'motion_apply','connection_handle':1,'session_epoch':'session',
     'incarnation':'a'*32,'request_id':1,'sample':sample}
    with self.assertRaisesRegex(ValueError,'full-pose motion'):
     getattr(participant,operation)(command)
    self.assertEqual(called,[])
if __name__=='__main__':unittest.main()
