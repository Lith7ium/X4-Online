"""Synthetic X4 peer over real loopback UDP; no game is started."""
from pathlib import Path
import socket
import sys
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC

class IPC(unittest.TestCase):
 def test_wrong_binding_digest_fences_without_acceptance(self):
  server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0))
  peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0))
  self.addCleanup(server.close);self.addCleanup(peer.close)
  lease,attempt,epoch,generation='1'*32,'2'*32,'b'*32,'c'*32
  peer.sendto(f'R|{lease}|{attempt}|READY|{epoch}|{generation}'.encode(),server.getsockname())
  bridge=ExperimentalParticipantMotionIPC(server,enabled=True,lease=lease,attempt=attempt,epoch=epoch,
           generation=generation,guard=lambda:True,validate_peer=lambda p:p==peer.getsockname(),timeout=1)
  self.assertTrue(bridge.wait_ready())
  def fake():
   data,address=peer.recvfrom(769);parts=data.decode().split('|');parts[10]='0'*64
   peer.sendto('|'.join(['R',lease,attempt,'BOUND',*parts[4:11]]).encode(),address)
  worker=threading.Thread(target=fake);worker.start()
  value={'version':1,'epoch':epoch,'generation':generation,'index':1,'sequence':1,
         'sector_macro':'sector_a','source_time':1,'x':0,'y':0,'z':0,'velocity':None}
  with self.assertRaises(ValueError):bridge(value,False)
  worker.join(2);self.assertFalse(worker.is_alive());self.assertEqual(bridge.state,'failed')
 def test_unverified_peer_is_rejected(self):
  server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0))
  peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0))
  self.addCleanup(server.close);self.addCleanup(peer.close)
  lease,attempt,epoch,generation='1'*32,'2'*32,'b'*32,'c'*32
  peer.sendto(f'R|{lease}|{attempt}|READY|{epoch}|{generation}'.encode(),server.getsockname())
  bridge=ExperimentalParticipantMotionIPC(server,enabled=True,lease=lease,attempt=attempt,epoch=epoch,
           generation=generation,guard=lambda:True,validate_peer=lambda p:False,timeout=1)
  with self.assertRaises(RuntimeError):bridge.wait_ready()
  self.assertEqual(bridge.state,'failed')
class UnsupportedMotionVersion(unittest.TestCase):
    def test_v3_refused_before_request_increment_or_outgoing_bind(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(server.close)
        self.addCleanup(peer.close)
        server.bind(('127.0.0.1', 0))
        peer.bind(('127.0.0.1', 0))
        lease, attempt, epoch, generation = '1'*32, '2'*32, 'b'*32, 'c'*32
        peer.sendto(f'R|{lease}|{attempt}|READY|{epoch}|{generation}'.encode(), server.getsockname())
        bridge = ExperimentalParticipantMotionIPC(
            server, enabled=True, lease=lease, attempt=attempt, epoch=epoch,
            generation=generation, guard=lambda: True,
            validate_peer=lambda address: address == peer.getsockname(), timeout=1)
        self.assertTrue(bridge.wait_ready())
        value = dict(version=3, epoch=epoch, generation=generation, index=1, sequence=1,
                     sector_macro='sector_a', source_time=1, capture_time=10,
                     x=0, y=0, z=0, real_velocity=None)
        before = bridge._next
        with self.assertRaisesRegex(ValueError, 'real-time position motion binding is not implemented'):
            bridge(value, False)
        self.assertEqual(bridge._next, before)
        self.assertEqual(bridge.state, 'failed')
        peer.setblocking(False)
        with self.assertRaises(BlockingIOError):
            peer.recv(769)


if __name__=='__main__':unittest.main()
