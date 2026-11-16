"""Actual local TCP + UDP; simulated client X4 and externally asserted grant."""
import json,socket,threading,unittest
from unittest.mock import patch
from tools.dev import authority_client_authority_bind as binder
from tests import test_authority_experimental_tcp_motion as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_client_authority_motion import ExperimentalTCPClientAuthorityMotion
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient

class AuthorityTCPUDP(unittest.TestCase):
 def test_server_pull_reaches_only_pinned_udp_reader(self):
  case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp();self.addCleanup(case.doCleanups)
  peer=case.case.connect();case.case.offer_and_claim(peer)
  udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0))
  fake=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);fake.bind(('127.0.0.1',0))
  fake.connect(udp.getsockname());fake.settimeout(.1)
  self.addCleanup(udp.close);self.addCleanup(fake.close)
  grant={'session_epoch':'a'*32,'epoch':'b'*32,'generation':'c'*32,'index':1318,
         'sector_macro':'cluster_115_sector001_macro','token':'d'*32,'incarnation':'e'*32}
  stop=threading.Event();errors=[];packets=[]
  def x4():
   try:
    fake.send(('S|'+'1'*32+'|'+'2'*32+'|HELLO|'+grant['epoch']+'|'+grant['generation']).encode('ascii'))
    while not stop.is_set():
     try:p=fake.recv(769).decode('ascii').split('|')
     except socket.timeout:continue
     packets.append(p[3]);base=['S',p[1],p[2]]
     if p[3]=='BOUND':reply=base+['ATTACHED',p[4],p[5]]
     elif p[3]=='REGISTER_SAVED':reply=base+['SAVED_REGISTERED',p[4],p[5],p[6],'1318','10054']
     elif p[3]=='PULL':reply=base+['SAMPLE',p[4],p[5],p[6],'1318','1','cluster_115_sector001_macro','3','1','2','3','-','-','-']
     else:raise AssertionError('unexpected local operation')
     fake.send('|'.join(reply).encode('ascii'))
   except BaseException as e:
    if not stop.is_set():errors.append(e)
  def participant():
   bridge=None
   try:
    peer.settimeout(2);raw=b''
    while not raw.endswith(b'\n'):raw+=peer.recv(1)
    assert json.loads(raw)['kind']=='accepted'
    bridge=binder.bind_client_authority(udp,process={'pid':9},lease='1'*32,attempt='2'*32,
      epoch=grant['epoch'],generation=grant['generation'],incarnation=grant['incarnation'],token=grant['token'],
      session_epoch=grant['session_epoch'],guard=lambda:True,running=lambda:True,
      grant=lambda e,g,n,t,i,s:(e,g,n,t,i,s)==(grant['epoch'],grant['generation'],grant['index'],grant['token'],grant['incarnation'],grant['session_epoch']),timeout=1)
    assert bridge.register_saved()
    app=ExperimentalTCPParticipantClient(peer,fixture.Controller(),enabled=True,epoch=grant['session_epoch'],handle=1,timeout=2,
       authority_grant=grant,authority_guard=lambda g:g==grant,pull_authority_motion=bridge.pull)
    while not stop.is_set():app.poll(.05)
    app.close();bridge.close()
   except BaseException as e:
    if not stop.is_set():errors.append(e)
  workers=[threading.Thread(target=x4),threading.Thread(target=participant)]
  process_patch=patch.object(binder,'check_process');socket_patch=patch.object(binder,'socket_owner',return_value=True)
  process_patch.start();socket_patch.start();self.addCleanup(process_patch.stop);self.addCleanup(socket_patch.stop)
  for thread in workers:thread.start()
  def finish():
   stop.set()
   for thread in workers:thread.join(2)
   self.assertFalse(any(t.is_alive() for t in workers));self.assertEqual(errors,[])
  self.addCleanup(finish)
  case.case.host.tick(.1);delivery=ExperimentalTCPJobDelivery(case.case.host,enabled=True,timeout=1)
  delivery._incarnations[1]=grant['incarnation']
  owner=ExperimentalTCPClientAuthorityMotion(delivery,enabled=True,grant=grant,guard=lambda g:g==grant)
  sample=owner.pull()
  self.assertEqual(sample['index'],1318);self.assertEqual(sample['sequence'],1);self.assertIsNone(sample['velocity'])
  self.assertEqual(packets,['BOUND','REGISTER_SAVED','PULL']);self.assertFalse(case.case.host._failed)
if __name__=='__main__':unittest.main()
