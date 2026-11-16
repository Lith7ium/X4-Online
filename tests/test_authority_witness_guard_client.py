"""Small real helper and checkpoint tests; no native X4."""
import gzip
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev'),str(ROOT/'tests')]
from authority.checkpoints import CheckpointStore
from test_authority_witness_source_guard import source_xml, MARKER
import authority_witness_guard_client as client
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import read_line, send_frame, parse_json

@unittest.skipUnless(sys.platform=='linux' and hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal'),'Linux pidfd required')
class GuardHelper(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'store').mkdir();self.store=CheckpointStore(self.root/'store')
        source=self.root/'save.gz';source.write_bytes(gzip.compress(source_xml().encode()))
        self.cp=self.store.publish(source,marker=MARKER);self.store.confirm(self.cp)
        self.registry=[];self.pumps=0
    def pump(self):self.pumps+=1
    def start(self,**kw):
        return client.WitnessGuardClient(self.store,self.cp,registry=self.registry,pump=self.pump,
            deadline=time.monotonic()+kw.get('deadline',5),timeout=kw.get('timeout',2))
    def test_full_guard_check_and_clean_correlated_stop(self):
        g=self.start();self.addCleanup(g._cleanup)
        self.assertEqual(g.status[:3],('ready','a'*32,2))
        self.assertTrue(g.check());self.assertTrue(g.check());self.assertTrue(g.stop())
        self.assertEqual(g.state,'stopped');self.assertEqual(g.helper.proc.returncode,0)
        self.assertIsNone(g.helper.pidfd);self.assertGreater(self.pumps,0)
    def test_pointer_mutation_faults_and_reaps(self):
        g=self.start();self.addCleanup(g._cleanup)
        p=self.store.directory/'CURRENT';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaises((RuntimeError,ValueError,TimeoutError)):g.check()
        self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
        self.assertIsNotNone(g.helper.proc.poll())
    def test_dead_helper_fails_closed(self):
        g=self.start();self.addCleanup(g._cleanup);g.helper.proc.kill();g.helper.proc.wait()
        with self.assertRaises(RuntimeError):g.check()
        self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
    def test_initialization_deadline_and_pumping(self):
        script=self.root/'slow.py';script.write_text('import time\ntime.sleep(10)\n')
        with patch.object(client,'READER',script):
            with self.assertRaises((TimeoutError,RuntimeError)):self.start(deadline=.3,timeout=.1)
        self.assertGreater(self.pumps,0)
        self.assertIsNotNone(self.registry[0].proc.poll());self.assertIsNone(self.registry[0].pidfd)
    def test_check_timeout_correlated_protocol_and_cleanup(self):
        script=self.root/'stall.py';script.write_text('''import json,socket,sys,time
s=socket.socket(fileno=int(sys.argv[1]));f=s.makefile('rb');c=json.loads(f.readline())
s.sendall((json.dumps(dict(token=c['token'],seq=0,event='READY',status=['ready','a'*32,2,'b'*64]))+'\\n').encode())
f.readline();time.sleep(10)
''')
        with patch.object(client,'READER',script):
            g=self.start(timeout=.2);self.addCleanup(g._cleanup)
            with self.assertRaises(TimeoutError):g.check()
        self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
        self.assertIsNotNone(g.helper.proc.poll())
    def test_wrong_correlation_faults(self):
        script=self.root/'wrong.py';script.write_text('''import json,socket,sys,time
s=socket.socket(fileno=int(sys.argv[1]));f=s.makefile('rb');c=json.loads(f.readline())
s.sendall((json.dumps(dict(token=c['token'],seq=0,event='READY',status=['ready','a'*32,2,'b'*64]))+'\\n').encode())
r=json.loads(f.readline());s.sendall((json.dumps(dict(token=r['token'],seq=r['seq']+1,event='CHECKED'))+'\\n').encode())
time.sleep(10)
''')
        with patch.object(client,'READER',script):
            g=self.start();self.addCleanup(g._cleanup)
            with self.assertRaises(ValueError):g.check()
        self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
    def test_pump_reentry_cannot_restore_failed_state(self):
        g=self.start();self.addCleanup(g._cleanup);attempted=[]
        def reenter():
            if not attempted:
                attempted.append(True)
                try:g.check()
                except RuntimeError:pass
        g.pump=reenter
        with self.assertRaises(RuntimeError):g.check()
        self.assertEqual(attempted,[True]);self.assertEqual(g.state,'failed');self.assertIsNone(g.helper.pidfd)
    def test_oversized_or_unsolicited_response_faults(self):
        for value in ('oversized','duplicate'):
            with self.subTest(value=value):
                script=self.root/(value+'.py')
                response="b'x'*1026" if value=='oversized' else "b'{}\\n{}\\n'"
                script.write_text("import socket,sys,time\ns=socket.socket(fileno=int(sys.argv[1]));s.recv(4096)\ns.sendall("+response+")\ntime.sleep(10)\n")
                with patch.object(client,'READER',script):
                    with self.assertRaises(ValueError):self.start()
                self.assertIsNotNone(self.registry[-1].proc.poll());self.assertIsNone(self.registry[-1].pidfd)
    def test_replaced_ipc_descriptor_is_detached_not_closed(self):
        g=self.start();self.addCleanup(g._cleanup)
        fd=g.fd;read,write=os.pipe()
        try:
            os.dup2(read,fd)
            with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):g.check()
            os.fstat(fd)
            self.assertIsNone(g.helper.pidfd)
        finally:
            os.close(fd);os.close(read);os.close(write)

    def test_reader_rejects_wrong_token_sequence_and_post_stop_frame(self):
        for case in ('token','sequence','after_stop'):
            with self.subTest(case=case):
                parent,child=socket.socketpair();self.addCleanup(parent.close)
                helper=OwnedHelper([sys.executable,str(client.READER),str(child.fileno())],
                    registry=self.registry,pass_fds=(child.fileno(),))
                try:
                    child.close();parent.setblocking(False);helper.release();deadline=time.monotonic()+4
                    token='e'*32
                    config={'mode':'witness_guard','store':str(self.store.directory),'token':token,'deadline':deadline}
                    config.update({key:str(getattr(self.cp,key)) if key=='path' else getattr(self.cp,key)
                                   for key in ('checkpoint_id','path','sha256','size','marker')})
                    def send(value):send_frame(parent,json.dumps(value).encode(),deadline,lambda:None)
                    def read():return parse_json(read_line(parent,1024,deadline))
                    send(config);self.assertEqual(read()['event'],'READY')
                    request={'token':token,'seq':1,'op':'CHECK'}
                    if case=='token':request['token']='f'*32
                    elif case=='sequence':request['seq']=2
                    else:request['op']='STOP'
                    send(request)
                    if case=='after_stop':
                        self.assertEqual(read()['event'],'STOPPED');send({'token':token,'seq':2,'op':'CHECK'})
                    self.assertNotEqual(helper.proc.wait(timeout=3),0)
                finally:
                    child.close();parent.close();helper.stop()
