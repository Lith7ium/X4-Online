"""Full worker wiring against separate owned fake X4 UDP peers, no game start."""
import json, os, subprocess, sys, time, unittest
from tests.test_authority_source_to_tcp_worker import SOURCE_SCRIPT, CLIENT_SCRIPT, identity, udp
import authority_source_motion_tcp_worker as worker

SOURCE = SOURCE_SCRIPT.replace(
 "count=int(os.environ.get('COUNT','1'));seq=1;end=time.monotonic()+10",
 "m=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);m.connect(('127.0.0.1',int(os.environ['MOTION'])))\n"
 "m.send(('S|'+'6'*32+'|'+'7'*32+'|HELLO'+suffix).encode())\n"
 "ready=False;samples=0;count=int(os.environ.get('COUNT','1'));seq=1;end=time.monotonic()+20")
SOURCE = SOURCE.replace('select.select([ctl,job]', 'select.select([ctl,job,m]')
SOURCE = SOURCE.replace("  elif v[3]=='BOUND':job.send", "  elif s is m:\n   if v[3]=='BOUND':m.send(('S|'+'6'*32+'|'+'7'*32+'|ATTACHED'+suffix).encode())\n   elif v[3]=='PULL':\n    answer=('S|'+'6'*32+'|'+'7'*32+'|')\n    if ready:\n     samples+=1\n     value='|10055|1|sector_a|2.5|1|2|3|-|-|-' if samples==1 else '|10055|2|sector_a|3|2|2|3|'+('3' if os.environ.get('BAD_RATE') else '2')+'|0|0'\n     answer+='SAMPLE'+suffix+'|'+v[-1]+value\n    else:answer+='NO_SAMPLE'+suffix+'|'+v[-1]\n    m.send(answer.encode())\n   else:raise AssertionError(v)\n  elif v[3]=='BOUND':job.send")
SOURCE = SOURCE.replace("  elif v[3]=='REARM':\n", "  elif v[3]=='REARM':\n   ready=True\n")
CLIENT = CLIENT_SCRIPT.replace("epoch='a'*32", "m=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);m.connect(('127.0.0.1',int(os.environ['MOTION'])))\nepoch='a'*32")
CLIENT = CLIENT.replace("end=time.monotonic()+5", "end=time.monotonic()+20")
CLIENT = CLIENT.replace('select.select([p,j]', 'select.select([p,j,m]')
CLIENT = CLIENT.replace("   j.send(('X|'+lease+'|'+attempt+'|READY|'+epoch+'|'+gen).encode())", "   j.send(('X|'+lease+'|'+attempt+'|READY|'+epoch+'|'+gen).encode())\n   m.send(('R|'+'4'*32+'|'+'5'*32+'|READY|'+epoch+'|'+gen).encode())")
CLIENT = CLIENT.replace("  else:\n   assert v[0]=='P'", "  elif s is m:\n   assert v[0]=='M' and v[3]=='BIND'\n   if os.environ.get('MOTION_LOG'):\n    with open(os.environ['MOTION_LOG'],'a') as f:f.write(v[8]+'\\n')\n   m.send(('|'.join(['R','4'*32,'5'*32,'BOUND']+v[4:11])).encode())\n  else:\n   assert v[0]=='P'")

class MotionWorker(unittest.TestCase):
 def run_diagnostic(self,count,bad_rate=False):
  cc,cj,cm,sc,sj,sm=(udp() for _ in range(6))
  for sock in (cc,cj,cm,sc,sj,sm):self.addCleanup(sock.close)
  import socket
  private,other=socket.socketpair();self.addCleanup(private.close);self.addCleanup(other.close)
  import tempfile
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  evidence=os.path.join(tmp.name,'motion-binds')
  client=subprocess.Popen([sys.executable,'-c',CLIENT],env=dict(os.environ,P=str(cc.getsockname()[1]),J=str(cj.getsockname()[1]),MOTION=str(cm.getsockname()[1]),MOTION_LOG=evidence))
  source_env=dict(os.environ,CTL=str(sc.getsockname()[1]),JOB=str(sj.getsockname()[1]),MOTION=str(sm.getsockname()[1]))
  if bad_rate:source_env['BAD_RATE']='1'
  source=subprocess.Popen([sys.executable,'-c',SOURCE],env=source_env,stdout=subprocess.PIPE)
  def finish():
   for p in (client,source):
    if p.poll() is None:p.terminate()
    p.wait(timeout=3)
   source.stdout.close()
  self.addCleanup(finish)
  c={'version':1,'epoch':'e'*32,'lease':'b'*32,'attempt':'c'*32,'generation':'d'*32,
    'participant_lease':'f'*32,'client_process':identity(client),'deadline':time.monotonic()+70,
    'job_epoch':'a'*32,'source_lease':'1'*32,'source_attempt':'2'*32,
    'source_control_lease':'3'*32,'source_world_epoch':'e'*32,'source_process':identity(source),
    'index':10055,'sectors':['sector_a'],'client_motion_lease':'4'*32,'client_motion_attempt':'5'*32,
    'source_motion_lease':'6'*32,'source_motion_attempt':'7'*32,'motion_count':count}
  if bad_rate:
   with self.assertRaises(ValueError):worker.run(cc,cj,cm,sc,sj,sm,private,worker.config(json.dumps(c).encode()))
   with open(evidence) as f:self.assertEqual(f.read().splitlines(),['1'])
   return
  result=worker.run(cc,cj,cm,sc,sj,sm,private,worker.config(json.dumps(c).encode()))
  self.assertTrue(result['tcp_job_receipt']);self.assertTrue(result['source_md_ack_observed'])
  self.assertTrue(result['motion_client_bound_buffered']);self.assertFalse(result['motion_frame_identity_proven'])
  samples=[result['motion_sample']] if count==1 else result['motion_samples']
  self.assertEqual([s['sequence'] for s in samples],list(range(1,count+1)))
  self.assertTrue(all(s['index']==10055 for s in samples));self.assertIsNone(samples[0]['velocity'])
  if count==2:self.assertEqual(samples[1]['velocity'],{'x':2,'y':0,'z':0})

 def test_one_sample_keeps_legacy_shape(self):self.run_diagnostic(1)
 def test_two_samples_over_real_tcp_and_owned_udp_peers(self):self.run_diagnostic(2)
 def test_wrong_second_rate_is_fenced_before_client_bind(self):self.run_diagnostic(2,True)

if __name__=='__main__':unittest.main()
