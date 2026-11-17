"""Connected real UDP, simulated client X4; no game, grant or PID proof."""
from pathlib import Path
import socket
import sys
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_client_authority_motion_ipc import ExperimentalClientAuthorityMotionIPC as Bridge

class ClientMotionIPC(unittest.TestCase):
 def setup_bridge(self,include_orientation=False):
  sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
  peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0))
  sock.connect(peer.getsockname());peer.connect(sock.getsockname());peer.settimeout(1)
  self.addCleanup(sock.close);self.addCleanup(peer.close)
  live=[True];grant=[True];tokens=('1'*32,'2'*32,'3'*32,'4'*32,'5'*32)
  def make():return Bridge(sock,enabled=True,lease=tokens[0],attempt=tokens[1],epoch=tokens[2],generation=tokens[3],incarnation=tokens[4],
   guard=lambda:live[0],validate_peer=lambda p:p==peer.getsockname(),grant=lambda e,g,i,n:grant[0] and (e,g,i,n)==(*tokens[2:],1318),timeout=.2,include_orientation=include_orientation)
  return make(),peer,live,grant,make
 def exchange(self,peer,operation,kind,sequence=None,game='1',velocity=('-','-','-'),alter=None):
  def respond():
   p=peer.recv(769).decode().split('|');assert p[3]==operation
   response=['S',p[1],p[2],kind,p[4],p[5],p[6]]
   if kind=='SAVED_REGISTERED':response+=['1318','10054']
   elif kind=='SAMPLE':response+=['1318',str(sequence),'cluster_115_sector001_macro',game,'1','2','3',*velocity]
   elif kind=='SAMPLE2':response+=['1318',str(sequence),'cluster_115_sector001_macro',game,'1','2','3','0.1','0.2','0.3',*velocity,*(['-','-','-'] if velocity==('-','-','-') else ['0.4','0.5','0.6'])]
   if alter:alter(response)
   peer.send('|'.join(response).encode())
  worker=threading.Thread(target=respond);worker.start();return worker
 def registered(self,include_orientation=False):
  b,p,live,grant,make=self.setup_bridge(include_orientation);t=self.exchange(p,'REGISTER_SAVED','SAVED_REGISTERED')
  self.assertTrue(b.register_saved());t.join(1);self.assertFalse(t.is_alive());return b,p,live,grant,make
 def test_sequential_samples_and_no_sample(self):
  b,p,_,_,_=self.registered()
  t=self.exchange(p,'PULL','NO_SAMPLE');self.assertIsNone(b.pull());t.join(1)
  t=self.exchange(p,'PULL','SAMPLE',1);first=b.pull();t.join(1)
  self.assertEqual(first['sequence'],1);self.assertIsNone(first['velocity'])
  t=self.exchange(p,'PULL','SAMPLE',2,game='1.5',velocity=('0','1','-2'));second=b.pull();t.join(1)
  self.assertEqual(second['velocity'],{'x':0.,'y':1.,'z':-2.});b.close()
 def test_opt_in_orientation_and_angular_rate(self):
  b,p,_,_,_=self.registered(True)
  t=self.exchange(p,'PULL','SAMPLE2',1);first=b.pull();t.join(1)
  self.assertEqual(first['orientation'],{'yaw':.1,'pitch':.2,'roll':.3});self.assertIsNone(first['angular_rate'])
  t=self.exchange(p,'PULL','SAMPLE2',2,game='1.5',velocity=('0','1','-2'));second=b.pull();t.join(1)
  self.assertEqual(second['angular_rate'],{'yaw':.4,'pitch':.5,'roll':.6});b.close()
 def test_opt_in_rejects_wrong_version_or_partial_angular_rate(self):
  for mode in ('version','partial','mixed'):
   with self.subTest(mode=mode):
    b,p,_,_,_=self.registered(True)
    def alter(response):
     if mode=='partial':response[21]='0.5'
     if mode=='mixed':response[20:23]=['0','0','0']
    t=self.exchange(p,'PULL','SAMPLE' if mode=='version' else 'SAMPLE2',1,alter=alter)
    with self.assertRaises(ValueError):b.pull()
    t.join(1);self.assertEqual(b.state,'failed')
 def test_duplicate_socket_and_grant_loss(self):
  b,p,live,grant,make=self.registered()
  with self.assertRaises(ValueError):make()
  grant[0]=False
  with self.assertRaises(RuntimeError):b.pull()
  self.assertEqual(b.state,'failed');p.settimeout(.03)
  with self.assertRaises(socket.timeout):p.recv(769)
 def test_foreign_stale_and_bad_numeric_fault(self):
  for mode in ('request','index','sector','sequence','time','rate','partial_velocity'):
   with self.subTest(mode=mode):
    b,p,_,_,_=self.registered()
    t=self.exchange(p,'PULL','SAMPLE',1);b.pull();t.join(1)
    def alter(v):
     if mode=='request':v[6]='999'
     if mode=='index':v[7]='1319'
     if mode=='sector':v[9]='foreign_sector'
    t=self.exchange(p,'PULL','SAMPLE',1 if mode=='sequence' else 2,
      game='1' if mode=='time' else '2',velocity=('1e999','0','0') if mode=='rate' else (('-','0','-') if mode=='partial_velocity' else ('-','-','-')),alter=alter)
    with self.assertRaises((ValueError,RuntimeError)):b.pull()
    t.join(1);self.assertFalse(t.is_alive());self.assertEqual(b.state,'failed')
 def test_missing_packet_and_guard_reentrancy_fence(self):
  b,p,_,_,_=self.registered()
  with self.assertRaises(RuntimeError):b.pull()
  self.assertEqual(b.state,'failed')
  p.recv(769) # The abandoned request cannot be retried.
  b2,p2,live,grant,_=self.registered()
  def reenter():
   try:b2.pull()
   except RuntimeError:pass
   return True
  b2._guard=reenter
  with self.assertRaises((RuntimeError,OSError)):b2.pull()
  self.assertEqual(b2.state,'failed')

 def test_grant_revoked_by_later_guard_and_internal_mutations(self):
  for mode in ('grant_loss','epoch','incarnation','request_counter','sample_counter','request_type','sample_type'):
   with self.subTest(mode=mode):
    b,p,_,grant,_=self.registered();seen=[False];original_grant=b._grant
    def probe(*args):
     seen[0]=True;return original_grant(*args)
    def guard():
     if mode=='grant_loss' and seen[0]:grant[0]=False
     if mode=='epoch':b._epoch='f'*32
     if mode=='incarnation':b._incarnation='f'*32
     if mode=='request_counter':b._next+=1
     if mode=='sample_counter':b._sequence+=1
     if mode=='request_type':b._next=float(b._next)
     if mode=='sample_type':b._sequence=float(b._sequence)
     return True
    b._guard=guard;b._grant=probe
    with self.assertRaises(RuntimeError):b.pull()
    self.assertEqual(b.state,'failed');p.settimeout(.03)
    with self.assertRaises(socket.timeout):p.recv(769)

if __name__=='__main__':unittest.main()
