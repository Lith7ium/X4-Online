"""Real admitted loopback TCP, fake local samples; no X4 or writes."""
import json, threading, unittest
from tests import test_authority_experimental_tcp_motion as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_client_authority_motion import ExperimentalTCPClientAuthorityMotion
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient

class AuthorityTCP(unittest.TestCase):
 def setup_pair(self,values,*,client_guard=lambda grant:True,server_guard=lambda grant:True):
  case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp();self.addCleanup(case.doCleanups)
  peer=case.case.connect();case.case.offer_and_claim(peer);stop=threading.Event();errors=[];calls=[]
  grant={'session_epoch':'a'*32,'epoch':'b'*32,'generation':'c'*32,'index':10055,'sector_macro':'sector_a','token':'d'*32,'incarnation':'e'*32}
  def run():
   try:
    peer.settimeout(2);raw=b''
    while not raw.endswith(b'\n'):raw+=peer.recv(1)
    assert json.loads(raw)['kind']=='accepted'
    def pull():calls.append(1);return values.pop(0)
    app=ExperimentalTCPParticipantClient(peer,fixture.Controller(),enabled=True,epoch='a'*32,handle=1,timeout=2,
       authority_grant=grant,authority_guard=client_guard,pull_authority_motion=pull)
    while not stop.is_set():app.poll(.05)
    app.close()
   except BaseException as e:
    if not stop.is_set():errors.append(e)
  thread=threading.Thread(target=run);thread.start()
  def finish():stop.set();thread.join(2);self.assertFalse(thread.is_alive())
  self.addCleanup(finish)
  case.case.host.tick(.1);delivery=ExperimentalTCPJobDelivery(case.case.host,enabled=True,timeout=1)
  delivery._incarnations[1]=grant['incarnation']
  owner=ExperimentalTCPClientAuthorityMotion(delivery,enabled=True,grant=grant,guard=server_guard)
  return case,owner,delivery,calls,errors
 def test_empty_then_two_exact_samples_over_one_admitted_socket(self):
  first=fixture.MotionTCP.sample();second=fixture.MotionTCP.sample(seq=2,t=2,velocity={'x':0,'y':0,'z':0})
  case,owner,_,calls,_=self.setup_pair([None,first,second])
  self.assertIsNone(owner.pull());self.assertEqual(owner.pull(),first);self.assertEqual(owner.pull(),second)
  self.assertEqual(len(calls),3);self.assertFalse(case.case.host._failed)
 def test_replayed_sample_faults_without_external_effect(self):
  first=fixture.MotionTCP.sample();case,owner,_,calls,_=self.setup_pair([first,first])
  self.assertEqual(owner.pull(),first)
  with self.assertRaises((ValueError,RuntimeError,ConnectionError,OSError)):owner.pull()
  self.assertTrue(case.case.host._failed);self.assertEqual(len(calls),2)
 def test_changed_grant_or_invalid_callback_sample_fences(self):
  for bad in ({**fixture.MotionTCP.sample(),'sector_macro':'foreign'}, {**fixture.MotionTCP.sample(),'velocity':{'x':1,'y':0,'z':0}}):
   with self.subTest(bad=bad):
    case,owner,_,_,_=self.setup_pair([bad])
    with self.assertRaises((ValueError,RuntimeError,ConnectionError,OSError)):owner.pull()
    self.assertTrue(case.case.host._failed)
 def test_server_guard_mutation_fails_before_command(self):
  def mutate(grant):grant['index']=1;return True
  case,owner,_,calls,_=self.setup_pair([fixture.MotionTCP.sample()],server_guard=mutate)
  with self.assertRaises(RuntimeError):owner.pull()
  self.assertEqual(calls,[]);self.assertTrue(case.case.host._failed)
 def test_swallowed_reentrant_guard_fences_before_command(self):
  ref={}
  def attack(grant):
   try:ref['owner'].pull()
   except RuntimeError:pass
   return True
  case,owner,_,calls,_=self.setup_pair([fixture.MotionTCP.sample()],server_guard=attack);ref['owner']=owner
  with self.assertRaises(RuntimeError):owner.pull()
  self.assertEqual(calls,[]);self.assertTrue(case.case.host._failed)
 def test_client_guard_mutation_and_foreign_incarnation_fence(self):
  def mutate(grant):grant['index']=1;return True
  case,owner,_,calls,_=self.setup_pair([fixture.MotionTCP.sample()],client_guard=mutate)
  with self.assertRaises((ValueError,RuntimeError,ConnectionError,OSError)):owner.pull()
  self.assertEqual(calls,[]);self.assertTrue(case.case.host._failed)
  case,owner,_,calls,_=self.setup_pair([fixture.MotionTCP.sample()]);owner._grant['incarnation']='f'*32
  with self.assertRaises(RuntimeError):owner.pull()
  self.assertEqual(calls,[]);self.assertTrue(case.case.host._failed)
if __name__=='__main__':unittest.main()
