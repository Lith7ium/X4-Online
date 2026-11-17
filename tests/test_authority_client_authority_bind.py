"""Running-client correlation handshake over real UDP; process checks mocked."""
from pathlib import Path
import socket,sys,threading,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_client_authority_bind as subject

class Binding(unittest.TestCase):
 def setup_pair(self,*,lose_running=False,wrong_owner=False,fixture_slot=None,pin_peer=None):
  sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
  peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0));peer.connect(sock.getsockname());peer.settimeout(.5)
  self.addCleanup(sock.close);self.addCleanup(peer.close);live=[True];seen=[];errors=[]
  def responder():
   try:
    peer.send(('S|'+'1'*32+'|'+'2'*32+'|HELLO|'+'3'*32+'|'+'4'*32).encode())
    data=peer.recv(769).decode().split('|');seen.append(data[3]);assert data[3]=='BOUND'
    if lose_running:live[0]=False
    peer.send(('S|'+'1'*32+'|'+'2'*32+'|ATTACHED|'+'3'*32+'|'+'4'*32).encode())
    if lose_running:return
    for expected in ('REGISTER_SAVED','PULL'):
     data=peer.recv(769).decode().split('|');seen.append(data[3]);assert data[3]==expected
     response=['S',data[1],data[2],'SAVED_REGISTERED' if expected=='REGISTER_SAVED' else 'NO_SAMPLE',data[4],data[5],data[6]]
     if expected=='REGISTER_SAVED':response+=['1318','10054'] if fixture_slot is None else [str(fixture_slot+2),'4']
     peer.send('|'.join(response).encode())
   except socket.timeout:
    if not wrong_owner:errors.append('timeout')
   except BaseException as e:errors.append(repr(e))
  thread=threading.Thread(target=responder);thread.start();self.addCleanup(thread.join,2)
  context=dict(process={'pid':9},lease='1'*32,attempt='2'*32,epoch='3'*32,generation='4'*32,
    incarnation='5'*32,token='6'*32,session_epoch='a'*32,guard=lambda:True,running=lambda:live[0],
    grant=lambda e,g,n,t,i,s:(e,g,n,t,i,s)==('3'*32,'4'*32,1318 if fixture_slot is None else fixture_slot+2,'6'*32,'5'*32,'a'*32),timeout=.5)
  if pin_peer is not None:
   context['expected_peer']=peer.getsockname() if pin_peer else ('127.0.0.1', 1)
  if fixture_slot is not None:
   context.update(fixture_slot=fixture_slot,fixture_sector='cluster_01_sector001_macro',include_orientation=True)
  self.addCleanup(lambda:self.assertEqual(errors,[]))
  return sock,context,seen
 def test_running_bind_then_correlated_read_only_registration_and_pull(self):
  sock,context,seen=self.setup_pair()
  with patch.object(subject,'check_process'),patch.object(subject,'socket_owner',return_value=True):
   bridge=subject.bind_client_authority(sock,**context);self.assertTrue(bridge.register_saved());self.assertIsNone(bridge.pull());bridge.close()
  self.assertEqual(seen,['BOUND','REGISTER_SAVED','PULL'])
 def test_revoked_running_fails_before_handoff(self):
  sock,context,seen=self.setup_pair(lose_running=True)
  with patch.object(subject,'check_process'),patch.object(subject,'socket_owner',return_value=True):
   with self.assertRaises((RuntimeError,OSError)):subject.bind_client_authority(sock,**context)
  self.assertEqual(seen,['BOUND'])
 def test_fixture_slots_bind_matching_registry_index(self):
  for slot in (1,2):
   with self.subTest(slot=slot):
    sock,context,seen=self.setup_pair(fixture_slot=slot)
    with patch.object(subject,'check_process'),patch.object(subject,'socket_owner',return_value=True):
     bridge=subject.bind_client_authority(sock,**context)
     self.assertTrue(bridge.register_saved());self.assertIsNone(bridge.pull());bridge.close()
    self.assertEqual(seen,['BOUND','REGISTER_SAVED','PULL'])
 def test_ready_peer_is_required_for_hello(self):
  sock,context,seen=self.setup_pair(wrong_owner=True,pin_peer=False)
  with patch.object(subject,'check_process'),patch.object(subject,'socket_owner',return_value=True):
   with self.assertRaises(RuntimeError):subject.bind_client_authority(sock,**context)
  self.assertEqual(seen,[])
 def test_matching_ready_peer_allows_binding(self):
  sock,context,seen=self.setup_pair(pin_peer=True)
  with patch.object(subject,'check_process'),patch.object(subject,'socket_owner',return_value=True):
   bridge=subject.bind_client_authority(sock,**context)
   self.assertTrue(bridge.register_saved());self.assertIsNone(bridge.pull());bridge.close()
  self.assertEqual(seen,['BOUND','REGISTER_SAVED','PULL'])
 def test_wrong_udp_owner_fails_before_bound(self):
  sock,context,seen=self.setup_pair(wrong_owner=True)
  with patch.object(subject,'check_process'),patch.object(subject,'socket_owner',return_value=False):
   with self.assertRaises(RuntimeError):subject.bind_client_authority(sock,**context)
  self.assertEqual(seen,[])
 def test_grant_callback_revokes_running_before_bound(self):
  sock,context,seen=self.setup_pair(wrong_owner=True);live=[True]
  context['running']=lambda:live[0]
  def revoke(*args):live[0]=False;return True
  context['grant']=revoke
  with patch.object(subject,'check_process'),patch.object(subject,'socket_owner',return_value=True):
   with self.assertRaises(RuntimeError):subject.bind_client_authority(sock,**context)
  self.assertEqual(seen,[])
if __name__=='__main__':unittest.main()
