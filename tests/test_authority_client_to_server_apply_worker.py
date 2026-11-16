"""Real TCP/UDP with owned stand-ins; never starts X4."""
import json,os,socket,subprocess,sys,time,unittest,threading,types
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'tests')]
import authority_client_to_server_apply_worker as worker
from test_authority_client_authority_tcp_worker import SCRIPT
from test_authority_source_to_tcp_worker import udp,identity

SERVER=r'''
import os,select,socket,time
p=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);p.connect(('127.0.0.1',int(os.environ['P'])))
j=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);j.connect(('127.0.0.1',int(os.environ['J'])))
m=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);m.connect(('127.0.0.1',int(os.environ['M'])))
p.send(('HELLO|'+'5'*32+'|'+'e'*32).encode());end=time.monotonic()+20
while time.monotonic()<end:
 for s in select.select([p,j,m],[],[],.05)[0]:
  v=s.recv(769).decode().split('|')
  if s is p:
   assert v[0]=='CMD' and v[-1]=='resume'
   with open(os.environ['LOG'],'a') as f:f.write('RESUME\n')
   p.send(('|'.join(['RECEIPT',v[1],v[2],v[3],v[4],'confirmed'])).encode())
   j.send(('X|'+'6'*32+'|'+'7'*32+'|READY|'+'a'*32+'|'+'d'*32).encode())
   m.send(('R|'+'8'*32+'|'+'9'*32+'|READY|'+'a'*32+'|'+'d'*32).encode())
  elif s is j:raise AssertionError('job operation forbidden')
  else:
   assert v[0]=='M' and v[3] in ('BIND','PREFLIGHT','APPLY')
   with open(os.environ['LOG'],'a') as f:f.write(v[3]+':'+v[8]+'\n')
   kind={'BIND':'BOUND','PREFLIGHT':'PREFLIGHTED','APPLY':'APPLIED'}[v[3]]
   fields=v[4:11] if kind=='BOUND' else v[4:]
   if kind=='PREFLIGHTED':fields=fields+[os.environ.get('STATUS','READY')]
   m.send(('|'.join(['R','8'*32,'9'*32,kind]+fields)).encode())
'''
class Worker(unittest.TestCase):
 def case(self,status):
  import tempfile
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);log=Path(temp.name)/'ops'
  cc,cj,ca,sc,sj,sm=[udp() for _ in range(6)]
  for s in (cc,cj,ca,sc,sj,sm):self.addCleanup(s.close)
  x,y=socket.socketpair();self.addCleanup(x.close);self.addCleanup(y.close)
  fake=subprocess.Popen([sys.executable,'-c',SCRIPT],env=dict(os.environ,P=str(cc.getsockname()[1]),J=str(cj.getsockname()[1]),A=str(ca.getsockname()[1])))
  server=subprocess.Popen([sys.executable,'-c',SERVER],env=dict(os.environ,P=str(sc.getsockname()[1]),J=str(sj.getsockname()[1]),M=str(sm.getsockname()[1]),LOG=str(log),STATUS='NEAR' if status=='NEAR' else 'READY'))
  def cleanup():
   for proc in (fake,server):
    if proc.poll() is None:proc.terminate()
    proc.wait(timeout=3)
  self.addCleanup(cleanup)
  c={'version':1,'epoch':'e'*32,'lease':'b'*32,'attempt':'c'*32,'generation':'d'*32,
     'participant_lease':'f'*32,'job_epoch':'a'*32,'client_process':identity(fake),'server_process':identity(server),
     'deadline':time.monotonic()+18,'authority_lease':'1'*32,'authority_attempt':'2'*32,'incarnation':'3'*32,
     'grant_token':'4'*32,'sample_count':2,'server_participant_lease':'5'*32,'server_job_lease':'6'*32,
     'server_job_attempt':'7'*32,'server_motion_lease':'8'*32,'server_motion_attempt':'9'*32,
     'server_snapshot':{'role':'server','nonce':'0'*32,'epoch':'a'*32,'index':1318,'code':'WRG-830',
      'macro':'ship_ter_m_corvette_01_a_macro','faction':'pioneers','sector_macro':'cluster_115_sector001_macro',
     'game_time':3.,'position':[0. if status=='EXHAUST' else (-4.75 if status=='FOURTH' else -4.95),0.,0.]}}
  c=worker.config(json.dumps(c).encode())
  if status=='READY':
   result=worker.run(cc,cj,ca,sc,sj,sm,x,c);self.assertTrue(result['server_apply_receipt'])
   self.assertEqual(result['samples'][1]['sequence'],2)
   self.assertEqual(log.read_text().splitlines(),['RESUME','BIND:2','PREFLIGHT:2','APPLY:2'])
  elif status=='FOURTH':
   result=worker.run(cc,cj,ca,sc,sj,sm,x,c)
   self.assertEqual(result['selected_sequence'],4);self.assertEqual(len(result['samples']),4)
   self.assertEqual(log.read_text().splitlines(),['RESUME','BIND:4','PREFLIGHT:4','APPLY:4'])
  elif status=='NEAR':
   with self.assertRaises(Exception):worker.run(cc,cj,ca,sc,sj,sm,x,c)
   self.assertEqual(log.read_text().splitlines(),['RESUME','BIND:2','PREFLIGHT:2'])
  elif status=='EXHAUST':
   with self.assertRaises(Exception):worker.run(cc,cj,ca,sc,sj,sm,x,c)
   self.assertFalse(log.exists(),'no suitable sample must leave server paused and unwritten')
  elif status=='TIMEOUT':
   offset=[0.];owner=worker.ExperimentalTCPClientAuthorityMotion;original=owner.pull
   def delayed(obj):
    sample=original(obj);offset[0]=21.;return sample
   with patch.object(owner,'pull',delayed),patch.object(worker,'time',types.SimpleNamespace(monotonic=lambda:time.monotonic()+offset[0])):
    with self.assertRaises(Exception):worker.run(cc,cj,ca,sc,sj,sm,x,c)
   self.assertFalse(log.exists(),'expired search must not resume server')
  else:
   trigger=threading.Event();failed=threading.Event()
   adapter=worker.client.ExperimentalTCPParticipantClient
   original_poll=adapter.poll;original_preflight=worker.ExperimentalParticipantMotionIPC.preflight
   def broken_poll(obj,*args,**kwargs):
    if trigger.is_set():failed.set();raise RuntimeError('simulated reader failure')
    return original_poll(obj,*args,**kwargs)
   def after_preflight(obj,sample):
    result=original_preflight(obj,sample);trigger.set()
    if not failed.wait(2):raise RuntimeError('failure injection timed out')
    return result
   with patch.object(adapter,'poll',broken_poll),patch.object(worker.ExperimentalParticipantMotionIPC,'preflight',after_preflight):
    with self.assertRaises(Exception):worker.run(cc,cj,ca,sc,sj,sm,x,c)
   self.assertEqual(log.read_text().splitlines(),['RESUME','BIND:2','PREFLIGHT:2'])
 def test_ready_applies_only_second_sample(self):self.case('READY')
 def test_near_never_applies(self):self.case('NEAR')
 def test_participant_failure_after_preflight_never_applies(self):self.case('FAIL_THREAD')
 def test_candidate_limit_never_resumes(self):self.case('EXHAUST')
 def test_time_budget_never_resumes(self):self.case('TIMEOUT')
 def test_fourth_real_sample_is_selected(self):self.case('FOURTH')
if __name__=='__main__':unittest.main()
