"""Source selector over real UDP and admitted TCP; synthetic X4 peers."""
import socket, threading, unittest
from tests import test_authority_experimental_tcp_motion as tcp_fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC

class SourceSelector(unittest.TestCase):
 def setup_bridge(self, selector, samples):
  case=tcp_fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp();self.addCleanup(case.doCleanups)
  a=case.case.connect();b=case.case.connect();case.case.offer_and_claim(a);case.case.offer_and_claim(b)
  case.client(a,1);case.client(b,2);case.case.host.tick(.1)
  delivery=ExperimentalTCPJobDelivery(case.case.host,enabled=True,timeout=1)
  motion=ExperimentalTCPMotion(delivery,enabled=True,min_interval=1/240)
  local=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);local.bind(('127.0.0.1',0));self.addCleanup(local.close)
  remote=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);remote.bind(('127.0.0.1',0));self.addCleanup(remote.close)
  local.connect(remote.getsockname());remote.connect(local.getsockname())
  def source():
   remote.settimeout(2)
   for seq,t,sector,velocity in samples:
    try:packet=remote.recv(769).decode().split('|')
    except (OSError,TimeoutError):return
    response=['S','1'*32,'2'*32,'SAMPLE','b'*32,'c'*32,packet[-1],'10055',str(seq),sector,str(t),'1','2','3',*velocity]
    try:remote.send('|'.join(response).encode())
    except OSError:return
  thread=threading.Thread(target=source);thread.start();self.addCleanup(thread.join,3)
  bridge=ExperimentalSourceMotionIPC(local,motion,enabled=True,lease='1'*32,attempt='2'*32,epoch='b'*32,generation='c'*32,
   guard=lambda:True,validate_peer=lambda p:p==remote.getsockname(),timeout=2,select_recipients=selector)
  bridge.bind_confirmed(10055)
  return case,delivery,bridge
 def test_empty_then_two_selected_clients_without_false_receipt(self):
  def choose(sample,members):return [] if sample['sequence']==1 else [members[sample['sequence']-2]]
  case,_,bridge=self.setup_bridge(choose,[(1,1,'sector_a',['-']*3),(2,2,'sector_a',['-']*3),(3,3,'sector_a',['-']*3)])
  self.assertIsNone(bridge.pull());self.assertEqual(case.received,[])
  self.assertEqual(bridge.pull()['sequence'],2);self.assertEqual(bridge.pull()['sequence'],3)
  self.assertEqual([(v[0],v[1]['sequence']) for v in case.received],[(1,2),(2,3)])
  bridge.close()
 def reject_skipped_regression(self,second):
  case,_,bridge=self.setup_bridge(lambda *_:[],[(2,2,'sector_a',['-']*3),second])
  self.assertIsNone(bridge.pull())
  with self.assertRaises(ValueError):bridge.pull()
  self.assertEqual(case.received,[]);self.assertTrue(case.case.host._failed)
 def test_skipped_sample_still_fences_sequence(self):self.reject_skipped_regression((2,3,'sector_a',['-']*3))
 def test_skipped_sample_still_fences_time(self):self.reject_skipped_regression((3,2,'sector_a',['-']*3))
 def test_skipped_sample_still_fences_frame_rate(self):self.reject_skipped_regression((3,3,'sector_b',['1','0','0']))
 def reject_selector(self,selector):
  case,_,bridge=self.setup_bridge(selector,[(1,1,'sector_a',['-']*3)])
  with self.assertRaises((ValueError,RuntimeError)):bridge.pull()
  self.assertEqual(case.received,[]);self.assertTrue(case.case.host._failed)
 def test_sample_mutation_faults(self):
  def select(value,members):value['x']=5;return members
  self.reject_selector(select)
 def test_membership_argument_mutation_faults(self):
  def select(value,members):members[0]['id']='peer_999';return members
  self.reject_selector(select)
 def test_foreign_or_old_incarnation_faults(self):
  def select(value,members):return [{**members[0],'incarnation':'0'*32}]
  self.reject_selector(select)
 def test_duplicate_faults(self):
  def select(value,members):return [members[0],members[0]]
  self.reject_selector(select)
 def test_reentrant_control_poll_is_blocked(self):
  ref={};blocked=[]
  def select(value,members):
   try:ref['delivery']._host._control.poll(0)
   except RuntimeError:blocked.append(True)
   return [members[0]]
  case,delivery,bridge=self.setup_bridge(select,[(1,1,'sector_a',['-']*3)])
  ref['delivery']=delivery;self.assertEqual(bridge.pull()['sequence'],1)
  self.assertEqual(blocked,[True]);self.assertEqual([v[0] for v in case.received],[1]);bridge.close()
 def test_incarnation_mutation_during_selector_faults(self):
  ref={}
  def select(value,members):ref['delivery']._incarnations[1]='0'*32;return [members[0]]
  case,delivery,bridge=self.setup_bridge(select,[(1,1,'sector_a',['-']*3)])
  ref['delivery']=delivery
  with self.assertRaises(RuntimeError):bridge.pull()
  self.assertEqual(case.received,[]);self.assertTrue(case.case.host._failed)

if __name__=='__main__':unittest.main()
