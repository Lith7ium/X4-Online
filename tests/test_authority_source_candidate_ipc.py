"""Correlated candidate request over the existing source UDP owner."""
import socket
import threading
import unittest
from tests import test_authority_experimental_tcp_motion as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC

class CandidateIPC(unittest.TestCase):
 def make(self, enabled=True):
  case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp();self.addCleanup(case.doCleanups)
  delivery=ExperimentalTCPJobDelivery(case.case.host,enabled=True,timeout=.05)
  motion=ExperimentalTCPMotion(delivery,enabled=True)
  a=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);a.bind(('127.0.0.1',0));self.addCleanup(a.close)
  b=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);b.bind(('127.0.0.1',0));self.addCleanup(b.close)
  a.connect(b.getsockname());b.connect(a.getsockname());b.settimeout(.4)
  bridge=ExperimentalSourceMotionIPC(a,motion,enabled=True,lease='1'*32,attempt='2'*32,epoch='b'*32,generation='c'*32,
    guard=lambda:True,validate_peer=lambda p:p==b.getsockname(),timeout=.25,stop_enabled=True,
    saved_baseline=100,saved_guard=lambda e,n:e=='b'*32 and n==100,candidate_indices=(1,42) if enabled else None)
  return case,bridge,b
 def reply(self,b,kind='candidate',value='42',request=None,epoch=None):
  packet=b.recv(769).decode().split('|');self.assertEqual(packet[3],'CANDIDATE')
  b.send('|'.join(['S','1'*32,'2'*32,'CANDIDATE',epoch or 'b'*32,'c'*32,request or packet[6],kind,value]).encode())
 def test_request_is_correlated_and_gate_accepts_only_chosen_index(self):
  case,bridge,peer=self.make();thread=threading.Thread(target=self.reply,args=(peer,));thread.start()
  self.assertEqual(bridge.request_candidate(),42);thread.join(1)
  with self.assertRaises(RuntimeError):bridge.register_saved(1)
  self.assertTrue(case.case.host._failed)
 def test_unsolicited_or_inconclusive_or_forged_results_fence(self):
  for kind,value,request,epoch in [('candidate','3',None,None),('candidate','42','9',None),
      ('candidate','42',None,'f'*32),('inconclusive','no_candidate',None,None),('inconclusive','unknown',None,None)]:
   with self.subTest(kind=kind,value=value,request=request,epoch=epoch):
    case,bridge,peer=self.make();thread=threading.Thread(target=self.reply,args=(peer,kind,value,request,epoch));thread.start()
    with self.assertRaises((RuntimeError,ValueError)):bridge.request_candidate()
    thread.join(1);self.assertTrue(case.case.host._failed)
 def test_candidate_required_before_register_or_pull(self):
  for operation in ('register','pull'):
   case,bridge,peer=self.make()
   with self.assertRaises(RuntimeError):bridge.register_saved(1) if operation=='register' else bridge.pull()
   self.assertTrue(case.case.host._failed)
   with self.assertRaises(TimeoutError):peer.recv(769)
 def test_standard_source_rejects_request_without_mutation(self):
  case,bridge,peer=self.make(enabled=False)
  with self.assertRaisesRegex(RuntimeError,'not enabled'):bridge.request_candidate()
  self.assertEqual(bridge.state,'ready');self.assertFalse(case.case.host._failed)
  with self.assertRaises(TimeoutError):peer.recv(769)
 def test_timeout_faults_and_queued_packet_is_never_accepted(self):
  for queued in (False,True):
   case,bridge,peer=self.make()
   if queued:peer.send(b'unrequested report')
   with self.assertRaises(RuntimeError):bridge.request_candidate()
   self.assertEqual(bridge.state,'failed');self.assertTrue(case.case.host._failed)
