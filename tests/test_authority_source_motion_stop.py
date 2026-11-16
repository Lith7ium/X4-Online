"""STOP handshake on real UDP with simulated X4; no game is started."""
import socket
import threading
import unittest
from tests import test_authority_experimental_tcp_motion as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC

class StopTests(unittest.TestCase):
 def setUp(self):
  self.case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');self.case.setUp();self.addCleanup(self.case.doCleanups)
  self.host=self.case.case.host
  delivery=ExperimentalTCPJobDelivery(self.host,enabled=True,timeout=.05)
  motion=ExperimentalTCPMotion(delivery,enabled=True)
  self.local=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.local.bind(('127.0.0.1',0));self.addCleanup(self.local.close)
  self.remote=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.remote.bind(('127.0.0.1',0));self.addCleanup(self.remote.close)
  self.local.connect(self.remote.getsockname());self.remote.connect(self.local.getsockname());self.remote.settimeout(.4)
  self.bridge=ExperimentalSourceMotionIPC(self.local,motion,enabled=True,lease='1'*32,attempt='2'*32,
    epoch='b'*32,generation='c'*32,guard=lambda:True,validate_peer=lambda p:p==self.remote.getsockname(),
    timeout=.2,stop_enabled=True)
 def test_correlated_stop_and_local_close(self):
  received=[]
  def peer():
   p=self.remote.recv(769).decode().split('|');received.append(p)
   self.remote.send('|'.join(['S','1'*32,'2'*32,'STOPPED','b'*32,'c'*32,p[6]]).encode())
  thread=threading.Thread(target=peer);thread.start()
  self.assertTrue(self.bridge.stop_remote());thread.join(1)
  self.assertEqual((received[0][3],received[0][6]),('STOP','1'))
  self.assertEqual(self.bridge.state,'remote_stopped');self.assertFalse(self.host._failed)
  self.bridge.close();self.assertEqual(self.bridge.state,'closed')
 def test_wrong_reply_faults_host(self):
  def peer():
   self.remote.recv(769)
   self.remote.send('|'.join(['S','1'*32,'2'*32,'STOPPED','b'*32,'c'*32,'9']).encode())
  thread=threading.Thread(target=peer);thread.start()
  with self.assertRaises(ValueError):self.bridge.stop_remote()
  thread.join(1);self.assertEqual(self.bridge.state,'failed');self.assertTrue(self.host._failed)
 def test_missing_reply_faults_host(self):
  with self.assertRaises(RuntimeError):self.bridge.stop_remote()
  self.assertEqual(self.bridge.state,'failed');self.assertTrue(self.host._failed)

 def test_queued_packet_fails_before_stop_dispatch(self):
  self.remote.send(b'unexpected')
  with self.assertRaises(RuntimeError):self.bridge.stop_remote()
  self.assertTrue(self.host._failed)
  with self.assertRaises(TimeoutError):self.remote.recv(769)
 def test_disabled_stop_refused_without_dispatch(self):
  self.bridge._stop_enabled=False
  with self.assertRaisesRegex(RuntimeError,'not enabled'):self.bridge.stop_remote()
  self.assertFalse(self.host._failed)
  with self.assertRaises(TimeoutError):self.remote.recv(769)
 def test_enabled_stop_cannot_be_bypassed_by_local_close(self):
  with self.assertRaisesRegex(RuntimeError,'without confirmed remote stop'):self.bridge.close()
  self.assertTrue(self.host._failed)

 def test_non_owner_is_fenced(self):
  seen=[]
  def wrong_thread():
   try:self.bridge.stop_remote()
   except RuntimeError as e:seen.append(str(e))
  t=threading.Thread(target=wrong_thread);t.start();t.join(1)
  self.assertTrue(seen);self.assertTrue(self.host._failed)
  with self.assertRaises(TimeoutError):self.remote.recv(769)

 def test_inflight_source_work_is_fenced(self):
  self.bridge._state='pulling'
  with self.assertRaisesRegex(RuntimeError,'cannot stop'):self.bridge.stop_remote()
  self.assertTrue(self.host._failed)
  with self.assertRaises(TimeoutError):self.remote.recv(769)

if __name__=='__main__':unittest.main()
