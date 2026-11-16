"""Supervisor socket chain with an owned Python stand-in, never an X4 run."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_tcp_job_client_live as worker
import authority_tcp_native_worker as native

SCRIPT=r'''
import os,select,socket,time
p=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);p.connect(('127.0.0.1',int(os.environ['P'])))
j=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);j.connect(('127.0.0.1',int(os.environ['J'])))
epoch='a'*32;lease='b'*32;attempt='c'*32;gen='d'*32;world='e'*32;pl='f'*32
p.send(('HELLO|'+pl+'|'+world).encode());end=time.monotonic()+5
while time.monotonic()<end:
 for s in select.select([p,j],[],[],.05)[0]:
  v=s.recv(769).decode().split('|')
  if s is p:
   assert v[0]=='CMD' and v[-1]=='resume'
   p.send(('|'.join(['RECEIPT',v[1],v[2],v[3],v[4],'confirmed'])).encode())
   j.send(('X|'+lease+'|'+attempt+'|READY|'+epoch+'|'+gen).encode())
  else:
   assert v[0]=='P' and v[3]=='APPLY'
   time.sleep(.03);j.send(('|'.join(['X',lease,attempt,'APPLIED']+v[4:10])).encode())
'''

class Supervisor(unittest.TestCase):
 def test_real_tcp_udp_chain_and_proc_socket_binding(self):
  p=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);p.bind(('127.0.0.1',0));self.addCleanup(p.close)
  j=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);j.bind(('127.0.0.1',0));self.addCleanup(j.close)
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  proc=subprocess.Popen([sys.executable,'-c',SCRIPT],env=dict(os.environ,P=str(p.getsockname()[1]),J=str(j.getsockname()[1])))
  def finish():
   if proc.poll() is None:proc.terminate()
   proc.wait(timeout=3)
  self.addCleanup(finish)
  st=Path('/proc')/str(proc.pid);image=(st/'exe').stat();fields=(st/'stat').read_text().rsplit(')',1)[1].split()
  process={'pid':proc.pid,'start_ticks':int(fields[19]),'exe_dev':image.st_dev,'exe_ino':image.st_ino}
  event={'epoch':'a'*32,'generation':'d'*32,'sequence':1,'index':10055,'descriptor':{
      'macro':'ship_a','faction':'argon','sector_macro':'sector_a','x':1,'y':2,'z':3}}
  c={'version':1,'epoch':'e'*32,'lease':'b'*32,'attempt':'c'*32,'generation':'d'*32,
     'participant_lease':'f'*32,'client_process':process,'deadline':time.monotonic()+10.5,'event':event}
  result=worker.run(p,j,a,c,event)
  self.assertTrue(result['tcp_admitted']);self.assertTrue(result['tcp_job_receipt'])
  self.assertTrue(result['synthetic_server_and_checkpoint']);self.assertFalse(result['checkpoint_offered_to_x4'])

 def test_worker_cli_inherited_fds_and_one_result(self):
  p=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);p.bind(('127.0.0.1',0));self.addCleanup(p.close)
  j=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);j.bind(('127.0.0.1',0));self.addCleanup(j.close)
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close);a.settimeout(5)
  fake=subprocess.Popen([sys.executable,'-c',SCRIPT],env=dict(os.environ,P=str(p.getsockname()[1]),J=str(j.getsockname()[1])))
  def finish():
   if fake.poll() is None:fake.terminate()
   fake.wait(timeout=3)
  self.addCleanup(finish)
  st=Path('/proc')/str(fake.pid);image=(st/'exe').stat();fields=(st/'stat').read_text().rsplit(')',1)[1].split()
  process={'pid':fake.pid,'start_ticks':int(fields[19]),'exe_dev':image.st_dev,'exe_ino':image.st_ino}
  event={'epoch':'a'*32,'generation':'d'*32,'sequence':1,'index':10055,'descriptor':{
      'macro':'ship_a','faction':'argon','sector_macro':'sector_a','x':1,'y':2,'z':3}}
  c={'version':1,'epoch':'e'*32,'lease':'b'*32,'attempt':'c'*32,'generation':'d'*32,
     'participant_lease':'f'*32,'client_process':process,'deadline':time.monotonic()+20,'event':event}
  fds=(p.fileno(),j.fileno(),b.fileno())
  child=subprocess.Popen([sys.executable,str(ROOT/'tools/dev/authority_tcp_job_client_live.py'),*(str(fd) for fd in fds)],pass_fds=fds)
  self.addCleanup(lambda:child.kill() if child.poll() is None else None)
  b.close();p.close();j.close()
  a.sendall(json.dumps(c).encode()+b'\n');data=b''
  while b'\n' not in data:
   chunk=a.recv(4096);self.assertTrue(chunk);data+=chunk
  result=json.loads(data);self.assertTrue(result['ok']);self.assertTrue(result['tcp_job_receipt'])
  self.assertEqual(child.wait(timeout=3),0);self.assertEqual(a.recv(1),b'')

 def test_context_collisions_are_rejected(self):
  proc=Path('/proc')/str(os.getpid());image=(proc/'exe').stat();fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
  process={'pid':os.getpid(),'start_ticks':int(fields[19]),'exe_dev':image.st_dev,'exe_ino':image.st_ino}
  event={'epoch':'a'*32,'generation':'d'*32,'sequence':1,'index':10055,'descriptor':{
      'macro':'ship_a','faction':'argon','sector_macro':'sector_a','x':1,'y':2,'z':3}}
  c={'version':1,'epoch':'e'*32,'lease':'b'*32,'attempt':'c'*32,'generation':'d'*32,
     'participant_lease':'f'*32,'client_process':process,'deadline':time.monotonic()+30,'event':event}
  worker.config(json.dumps(c).encode())
  for field in ('epoch','participant_lease'):
   bad=dict(c,**{field:c['lease']})
   with self.assertRaises(ValueError):worker.config(json.dumps(bad).encode())

if __name__=='__main__':unittest.main()
