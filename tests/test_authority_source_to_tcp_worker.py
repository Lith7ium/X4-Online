"""Real host/TCP/UDP with two owned synthetic process peers; no X4 starts."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'tests')]
import authority_source_to_tcp_worker as worker
from test_authority_tcp_job_client_live import SCRIPT as CLIENT_SCRIPT

SOURCE_SCRIPT=r'''
import os,select,socket,time
ctl=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);ctl.connect(('127.0.0.1',int(os.environ['CTL'])))
job=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);job.connect(('127.0.0.1',int(os.environ['JOB'])))
lease='1'*32;attempt='2'*32;ctllease='3'*32;world='e'*32;epoch='a'*32;gen='d'*32
suffix='|'+epoch+'|'+gen
ctl.send(('HELLO|'+ctllease+'|'+world).encode());job.send(('S|'+lease+'|'+attempt+'|HELLO'+suffix).encode())
end=time.monotonic()+10
while time.monotonic()<end:
 for s in select.select([ctl,job],[],[],.05)[0]:
  v=s.recv(769).decode().split('|')
  if s is ctl:
   assert v[0]=='CMD' and v[-1]=='resume'
   ctl.send(('|'.join(['RECEIPT',v[1],v[2],v[3],v[4],'confirmed'])).encode())
   job.send(('S|'+lease+'|'+attempt+'|CANDIDATE|'+epoch+'|'+gen+'|1|10055|ship_a|argon|'+os.environ.get('SECTOR','sector_a')+'|1|2|3').encode())
  elif v[3]=='BOUND':job.send(('S|'+lease+'|'+attempt+'|ATTACHED'+suffix).encode())
  elif v[3]=='GO':job.send(('S|'+lease+'|'+attempt+'|GO_READY'+suffix).encode())
  elif v[3]=='BIND':
   print('BIND',flush=True)
   assert v[8]=='1' and v[9]=='peer_1';peer,inc=v[9],v[10]
   job.send(('S|'+lease+'|'+attempt+'|READY|'+epoch+'|'+gen+'|1|10055').encode())
  elif v[3]=='RECEIPT':
   assert v[8]==peer and v[9]==inc
   job.send(('S|'+lease+'|'+attempt+'|SOURCE_ACKED|'+epoch+'|'+gen+'|1|10055|'+peer+'|'+inc).encode())
  elif v[3]=='REARM':
   job.send(('S|'+lease+'|'+attempt+'|REARMED|'+epoch+'|'+gen+'|1|10055').encode())
  else:raise AssertionError(v)
'''

def udp():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',0));return s

def identity(proc):
    p=Path('/proc')/str(proc.pid);st=(p/'exe').stat();fields=(p/'stat').read_text().rsplit(')',1)[1].split()
    return {'pid':proc.pid,'start_ticks':int(fields[19]),'exe_dev':st.st_dev,'exe_ino':st.st_ino}

class SourceWorker(unittest.TestCase):
    def run_case(self,sector):
        cc,cj,sc,sj=(udp() for _ in range(4))
        for s in (cc,cj,sc,sj):self.addCleanup(s.close)
        private,other=socket.socketpair();self.addCleanup(private.close);self.addCleanup(other.close)
        client=subprocess.Popen([sys.executable,'-c',CLIENT_SCRIPT],env=dict(os.environ,P=str(cc.getsockname()[1]),J=str(cj.getsockname()[1])))
        source=subprocess.Popen([sys.executable,'-c',SOURCE_SCRIPT],env=dict(os.environ,CTL=str(sc.getsockname()[1]),JOB=str(sj.getsockname()[1]),SECTOR=sector),stdout=subprocess.PIPE)
        def stop():
            for proc in (client,source):
                if proc.poll() is None:proc.terminate()
                proc.wait(timeout=3)
            if source.stdout:source.stdout.close()
        self.addCleanup(stop)
        c={'version':1,'epoch':'e'*32,'lease':'b'*32,'attempt':'c'*32,'generation':'d'*32,
           'participant_lease':'f'*32,'client_process':identity(client),'deadline':time.monotonic()+50,
           'job_epoch':'a'*32,'source_lease':'1'*32,'source_attempt':'2'*32,
           'source_control_lease':'3'*32,'source_world_epoch':'e'*32,'source_process':identity(source),
           'index':10055,'sectors':['sector_a']}
        c=worker.config(json.dumps(c).encode())
        if sector=='sector_a':
            result=worker.run(cc,cj,sc,sj,private,c)
            self.assertTrue(result['tcp_job_receipt']);self.assertTrue(result['source_md_ack_observed'])
            self.assertTrue(result['synthetic_server_checkpoint_and_admission'])
            self.assertFalse(result['source_activation_is_birth']);self.assertEqual(result['sector_macro'],'sector_a')
        else:
            with self.assertRaises(ValueError):worker.run(cc,cj,sc,sj,private,c)
            source.terminate();source.wait(timeout=3)
            self.assertEqual(source.stdout.read(),b'') # no BIND, hence no TCP application

    def test_source_event_flows_through_real_admitted_tcp_and_back_to_source_ack(self):
        self.run_case('sector_a')

    def test_candidate_without_witness_fails_before_any_delivery(self):
        self.run_case('other_sector')

if __name__=='__main__':unittest.main()
