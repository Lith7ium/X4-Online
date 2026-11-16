"""Real loopback UDP with a simulated X4 owner; no X4 process or setter."""
from pathlib import Path
import socket
import sys
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC


class ApplyIPC(unittest.TestCase):
 def prepare(self,*,allow=True,peer_guard=None):
  local=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);local.bind(('127.0.0.1',0))
  peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0));peer.settimeout(1)
  self.addCleanup(local.close);self.addCleanup(peer.close)
  lease,attempt,epoch,generation='1'*32,'2'*32,'b'*32,'c'*32
  peer.sendto(f'R|{lease}|{attempt}|READY|{epoch}|{generation}'.encode(),local.getsockname())
  bridge=ExperimentalParticipantMotionIPC(local,enabled=True,lease=lease,attempt=attempt,epoch=epoch,
    generation=generation,guard=lambda:True,validate_peer=peer_guard or (lambda p:p==peer.getsockname()),
    timeout=.25,allow_apply=allow)
  self.assertTrue(bridge.wait_ready())
  sample={'version':1,'epoch':epoch,'generation':generation,'index':1318,'sequence':1,
    'sector_macro':'sector_a','source_time':1,'x':12,'y':-3,'z':7,'velocity':None}
  def bind():
   data,address=peer.recvfrom(769);parts=data.decode().split('|')
   peer.sendto('|'.join(['R',lease,attempt,'BOUND',*parts[4:11]]).encode(),address)
  worker=threading.Thread(target=bind);worker.start();self.assertTrue(bridge(sample,False));worker.join(1)
  self.assertFalse(worker.is_alive())
  return bridge,peer,sample

 def preflight(self,bridge,peer,sample,status='READY'):
  def answer():
   data,address=peer.recvfrom(769);p=data.decode().split('|')
   assert p[3]=='PREFLIGHT'
   peer.sendto('|'.join(['R',p[1],p[2],'PREFLIGHTED',*p[4:],status]).encode(),address)
  worker=threading.Thread(target=answer);worker.start()
  result=bridge.preflight(sample);worker.join(1);self.assertFalse(worker.is_alive())
  return result

 def test_successful_exact_response_and_one_shot(self):
  bridge,peer,sample=self.prepare();observed=[]
  self.assertEqual(self.preflight(bridge,peer,sample),'READY')
  def answer():
   data,address=peer.recvfrom(769);p=data.decode().split('|');observed.append(p)
   peer.sendto('|'.join(['R',p[1],p[2],'APPLIED',*p[4:]]).encode(),address)
  worker=threading.Thread(target=answer);worker.start()
  self.assertTrue(bridge.apply_once(sample));worker.join(1);self.assertFalse(worker.is_alive())
  self.assertEqual(observed[0][3],'APPLY');self.assertEqual(len(observed[0]),10)
  self.assertEqual(observed[0][5:9],[sample['epoch'],sample['generation'],'1318','1'])
  with self.assertRaises(RuntimeError):bridge.apply_once(sample)
  self.assertEqual(bridge.state,'failed')

 def test_default_disabled_and_altered_sample_never_send(self):
  for disabled in (True,False):
   bridge,peer,sample=self.prepare(allow=not disabled)
   if not disabled:self.assertEqual(self.preflight(bridge,peer,sample),'READY')
   sample=dict(sample)
   if not disabled:sample['x']+=1
   with self.assertRaises((ValueError,RuntimeError)):bridge.apply_once(sample)
   self.assertEqual(bridge.state,'failed');peer.settimeout(.03)
   with self.assertRaises(socket.timeout):peer.recvfrom(769)

 def test_foreign_response_and_missing_readback_fence(self):
  for missing in (False,True):
   bridge,peer,sample=self.prepare()
   self.assertEqual(self.preflight(bridge,peer,sample),'READY')
   def answer():
    data,address=peer.recvfrom(769);p=data.decode().split('|')
    if not missing:
     p[-1]='0'*64
     peer.sendto('|'.join(['R',p[1],p[2],'APPLIED',*p[4:]]).encode(),address)
   worker=threading.Thread(target=answer);worker.start()
   with self.assertRaises((ValueError,RuntimeError)):bridge.apply_once(sample)
   worker.join(1);self.assertFalse(worker.is_alive());self.assertEqual(bridge.state,'failed')

 def test_lost_peer_before_apply_fences_without_send(self):
  healthy=[True]
  bridge,peer,sample=self.prepare(peer_guard=lambda p:healthy[0])
  self.assertEqual(self.preflight(bridge,peer,sample),'READY')
  healthy[0]=False
  with self.assertRaises(RuntimeError):bridge.apply_once(sample)
  self.assertEqual(bridge.state,'failed');peer.settimeout(.03)
  with self.assertRaises(socket.timeout):peer.recvfrom(769)

 def test_near_preserves_apply_for_a_new_bound_sample(self):
  bridge,peer,sample=self.prepare();self.assertEqual(self.preflight(bridge,peer,sample,'NEAR'),'NEAR')
  newer=dict(sample,sequence=2,x=14)
  def bind():
   data,address=peer.recvfrom(769);p=data.decode().split('|')
   peer.sendto('|'.join(['R',p[1],p[2],'BOUND',*p[4:11]]).encode(),address)
  worker=threading.Thread(target=bind);worker.start();self.assertTrue(bridge(newer,False));worker.join(1)
  self.assertEqual(self.preflight(bridge,peer,newer),'READY')
  def answer():
   data,address=peer.recvfrom(769);p=data.decode().split('|')
   peer.sendto('|'.join(['R',p[1],p[2],'APPLIED',*p[4:]]).encode(),address)
  worker=threading.Thread(target=answer);worker.start();self.assertTrue(bridge.apply_once(newer));worker.join(1)

 def test_near_or_absent_preflight_cannot_apply(self):
  for near in (False,True):
   bridge,peer,sample=self.prepare()
   if near:self.assertEqual(self.preflight(bridge,peer,sample,'NEAR'),'NEAR')
   with self.assertRaises(ValueError):bridge.apply_once(sample)
   self.assertEqual(bridge.state,'failed');peer.settimeout(.03)
   with self.assertRaises(socket.timeout):peer.recvfrom(769)

 def test_preflight_replay_mismatch_and_timeout_fail_closed(self):
  for mode in ('replay','wrong_sample','bad_digest','timeout'):
   bridge,peer,sample=self.prepare()
   if mode=='replay':self.assertEqual(self.preflight(bridge,peer,sample,'NEAR'),'NEAR')
   if mode in ('bad_digest','timeout'):
    def answer():
     data,address=peer.recvfrom(769);p=data.decode().split('|')
     if mode=='bad_digest':
      p[-1]='0'*64
      peer.sendto('|'.join(['R',p[1],p[2],'PREFLIGHTED',*p[4:],'READY']).encode(),address)
    worker=threading.Thread(target=answer);worker.start()
   if mode=='wrong_sample':sample=dict(sample,x=13)
   with self.assertRaises((ValueError,RuntimeError)):bridge.preflight(sample)
   if mode in ('bad_digest','timeout'):worker.join(1);self.assertFalse(worker.is_alive())
   self.assertEqual(bridge.state,'failed')


if __name__=='__main__':unittest.main()
