"""Real TCP/UDP and owned fake processes; no X4, MD, or real grant."""
import json,os,socket,subprocess,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'tests')]
import authority_client_authority_tcp_worker as worker
from test_authority_source_to_tcp_worker import udp,identity

SCRIPT=r'''
import os,select,socket,time
p=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);p.connect(('127.0.0.1',int(os.environ['P'])))
j=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);j.connect(('127.0.0.1',int(os.environ['J'])))
a=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);a.connect(('127.0.0.1',int(os.environ['A'])))
epoch='a'*32;lease='b'*32;attempt='c'*32;gen='d'*32;world='e'*32;pl='f'*32;al='1'*32;at='2'*32
p.send(('HELLO|'+pl+'|'+world).encode());seq=0;polls=0;end=time.monotonic()+20
while time.monotonic()<end:
 for s in select.select([p,j,a],[],[],.05)[0]:
  v=s.recv(769).decode().split('|')
  if s is p:
   assert v[0]=='CMD' and v[-1]=='resume'
   p.send(('|'.join(['RECEIPT',v[1],v[2],v[3],v[4],'confirmed'])).encode())
   j.send(('X|'+lease+'|'+attempt+'|READY|'+epoch+'|'+gen).encode())
   a.send(('S|'+al+'|'+at+'|HELLO|'+epoch+'|'+gen).encode())
  elif s is j:raise AssertionError('unexpected job')
  elif v[3]=='BOUND':a.send(('S|'+al+'|'+at+'|ATTACHED|'+epoch+'|'+gen).encode())
  elif v[3]=='REGISTER_SAVED':
   assert v[7:]==['1318','10054']
   a.send(('|'.join(['S',al,at,'SAVED_REGISTERED',epoch,gen]+v[6:])).encode())
  elif v[3]=='PULL':
   polls+=1
   if polls==1:
    a.send(('|'.join(['S',al,at,'NO_SAMPLE',epoch,gen,v[6]])).encode())
    continue
   seq+=1
   n=seq if os.environ.get('BAD')!='1' else seq+1
   vel=['-','-','-'] if seq==1 else ['1','0','0']
   a.send(('|'.join(['S',al,at,'SAMPLE',epoch,gen,v[6],'1318',str(n),'cluster_115_sector001_macro',str(seq/10),str((seq-1)/10),'0','0']+vel)).encode())
  else:raise AssertionError(v)
'''
class Worker(unittest.TestCase):
 def case(self,bad=False,cli=False):
  p,j,a=udp(),udp(),udp()
  for s in (p,j,a):self.addCleanup(s.close)
  x,y=socket.socketpair();self.addCleanup(x.close);self.addCleanup(y.close)
  fake=subprocess.Popen([sys.executable,'-c',SCRIPT],env=dict(os.environ,P=str(p.getsockname()[1]),J=str(j.getsockname()[1]),A=str(a.getsockname()[1]),BAD='1' if bad else '0'))
  server=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
  def cleanup():
   for proc in (fake,server):
    if proc.poll() is None:proc.terminate()
    proc.wait(timeout=3)
  self.addCleanup(cleanup)
  c={'version':1,'epoch':'e'*32,'lease':'b'*32,'attempt':'c'*32,'generation':'d'*32,
     'participant_lease':'f'*32,'job_epoch':'a'*32,'client_process':identity(fake),'server_process':identity(server),
     'deadline':time.monotonic()+18,'authority_lease':'1'*32,'authority_attempt':'2'*32,'incarnation':'3'*32,
     'grant_token':'4'*32,'sample_count':2}
  c=worker.config(json.dumps(c).encode())
  if cli:
   fds=tuple(s.fileno() for s in (p,j,a,x))
   child=subprocess.Popen([sys.executable,str(ROOT/'tools/dev/authority_client_authority_tcp_worker.py'),*(str(fd) for fd in fds)],pass_fds=fds)
   self.addCleanup(lambda:child.kill() if child.poll() is None else None)
   for s in (p,j,a,x):s.close()
   y.settimeout(10);y.sendall(json.dumps(c).encode()+b'\n');data=b''
   while b'\n' not in data:
    chunk=y.recv(8192);self.assertTrue(chunk);data+=chunk
   result=json.loads(data);self.assertTrue(result['ok']);self.assertEqual(len(result['samples']),2)
   self.assertEqual(child.wait(timeout=3),0);self.assertEqual(y.recv(1),b'')
   return
  if bad:
   with self.assertRaises(Exception):worker.run(p,j,a,x,c)
  else:
   result=worker.run(p,j,a,x,c)
   self.assertTrue(result['client_authority_registered']);self.assertFalse(result['server_x4_motion_applied'])
   self.assertEqual([s['sequence'] for s in result['samples']],[1,2])
   self.assertIsNone(result['samples'][0]['velocity']);self.assertEqual(result['samples'][1]['velocity']['x'],1)
 def test_real_socket_chain_with_two_samples(self):self.case()
 def test_foreign_sequence_fails_closed(self):self.case(True)
 def test_inherited_fds_cli_returns_one_frame(self):self.case(cli=True)
if __name__=='__main__':unittest.main()
