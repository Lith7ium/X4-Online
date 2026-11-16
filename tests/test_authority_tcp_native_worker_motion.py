"""Real worker/TCP/UDP and Lua saved binding; X4 ABI and MD are simulated."""
import json
import os
from pathlib import Path
import shutil
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from authority.experimental_client_load import HonestClientLoadClaim
from authority.load_messages import Receipt
from authority.trusted_load_messages import encode_load_claim
from authority.experimental_tcp_motion import motion_digest
from test_authority_tcp_native_worker import line
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_tcp_native_worker as worker_module


def ident(pid):
    proc=Path('/proc')/str(pid);fields=(proc/'stat').read_text().rsplit(')',1)[1].split();image=(proc/'exe').stat()
    return dict(pid=pid,start_ticks=int(fields[19]),exe_dev=image.st_dev,exe_ino=image.st_ino)


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('luajit') and shutil.which('cc'),'Linux, LuaJIT and C compiler required')
class WorkerMotion(unittest.TestCase):
    def run_case(self, *, foreign_peer=False, paused=False, paused_after=False, stop_bound=False, deadline_bound=False, missing_config=False, identity_loss=False):
        sockets=[];children=[]
        try:
            with tempfile.TemporaryDirectory() as d:
                net,abi=Path(d)/'net.so',Path(d)/'abi.so'
                subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(net)],cwd=ROOT,check=True,capture_output=True)
                subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/replica_motion_binding_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
                listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);sockets.append(listener);listener.bind(('127.0.0.1',0));listener.listen(1)
                client=socket.create_connection(listener.getsockname(),timeout=2);sockets.append(client)
                server,_=listener.accept();sockets.append(server);server.settimeout(5)
                udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sockets.append(udp);udp.bind(('127.0.0.1',0))
                engine=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sockets.append(engine);engine.bind(('127.0.0.1',0));engine.settimeout(3)
                motion=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sockets.append(motion);motion.bind(('127.0.0.1',0))
                parent,child=socket.socketpair();sockets.extend([parent,child]);parent.settimeout(5)
                env=dict(os.environ,LD_PRELOAD=str(abi),TEST_NET_LIB=str(net),TEST_NET_PORT=str(motion.getsockname()[1]))
                if stop_bound or deadline_bound:env.update(TEST_MOTION_BIND_TRACE='1',TEST_MOTION_BIND_DELAY='4')
                lua=subprocess.Popen(['luajit','tests/authority_saved_motion_pair_client_fake_x4.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE);children.append(lua)
                identity=ident(os.getpid() if foreign_peer else lua.pid)
                fds=(client.fileno(),udp.fileno(),child.fileno(),motion.fileno())
                worker=subprocess.Popen([sys.executable,str(ROOT/'tools/dev/authority_tcp_native_worker.py'),*(str(x) for x in fds)],pass_fds=fds,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);children.append(worker)
                client.close();udp.close();child.close();motion.close()
                epoch,lease,attempt='9'*32,'8'*32,'7'*32
                receipt=Receipt(epoch,1,1,1,attempt,'checkpoint-'+'6'*32,'5'*64,10)
                claim=encode_load_claim(HonestClientLoadClaim(receipt,'4'*32,True,True))
                cfg={'version':1,'claim':claim.decode(),'epoch':epoch,'handle':1,'lease':lease,
                     'udp_peer':list(engine.getsockname()),'udp_next_id':1,'deadline':time.monotonic()+(2 if deadline_bound else 15),
                     'controller_timeout':9 if deadline_bound else 3,'client_process':identity,
                     'motion':{'lease':'a'*32,'attempt':'b'*32,'epoch':'c'*32,'generation':'d'*32,'timeout':4 if deadline_bound else 1}}
                if missing_config:
                    del cfg['motion'];parent.sendall(json.dumps(cfg).encode()+b'\n')
                    self.assertEqual(json.loads(line(parent)),{'event':'failed'});self.assertEqual(worker.wait(timeout=3),1);return
                parent.sendall(json.dumps(cfg).encode()+b'\n');self.assertEqual(line(server),claim)
                server.sendall(json.dumps({'version':1,'kind':'accepted','attempt_id':attempt}).encode()+b'\n')
                self.assertEqual(json.loads(line(parent)),{'event':'active'})
                def control(number,op):
                    command={'version':1,'kind':'participant_command','epoch':epoch,'connection_handle':1,'request_id':number,'operation':op}
                    server.sendall(json.dumps(command).encode()+b'\n')
                    raw,peer=engine.recvfrom(1024)
                    self.assertEqual(raw,f'CMD|{lease}|{epoch}|{number}|{op}'.encode())
                    engine.sendto(f'RECEIPT|{lease}|{epoch}|{number}|{op}|confirmed'.encode(),peer)
                    self.assertEqual(json.loads(line(server)),dict(command,kind='participant_receipt',status='confirmed'))
                if not paused:control(1,'resume')
                if identity_loss:
                    lua.terminate();lua.wait(timeout=3)
                    self.assertEqual(json.loads(line(parent)),{'event':'failed'})
                    self.assertEqual(worker.wait(timeout=3),1)
                    return
                def send_sample(seq):
                    sample={'version':1,'epoch':'c'*32,'generation':'d'*32,'index':42,'sequence':seq,'sector_macro':'sector_a',
                            'source_time':1 if seq==1 else 1.5,'x':seq,'y':2,'z':3,
                            'velocity':None if seq==1 else {'x':2,'y':0,'z':0}}
                    msg={'version':1,'kind':'motion_snapshot','connection_handle':1,'session_epoch':epoch,
                         'incarnation':'3'*32,'request_id':seq,'sample':sample}
                    server.sendall(json.dumps(msg).encode()+b'\n');return sample
                sample_sent=time.monotonic();sample=send_sample(1)
                if stop_bound or deadline_bound:
                    self.assertTrue(select.select([lua.stdout],[],[],2)[0], 'no BIND reached Lua')
                    self.assertEqual(lua.stdout.readline(),b'BIND\n')
                    bind_observed=time.monotonic()
                    if deadline_bound:
                        self.assertGreater(cfg['deadline'],bind_observed,'overall deadline expired before BIND')
                        self.assertLess(cfg['deadline']-bind_observed,cfg['motion']['timeout']-.25,
                                        'motion timeout might precede overall deadline')
                    if stop_bound:parent.sendall(b'{"command":"stop"}\n')
                    self.assertEqual(json.loads(line(parent)),{'event':'failed'})
                    failed_at=time.monotonic()
                    if deadline_bound:
                        self.assertGreaterEqual(failed_at,cfg['deadline'])
                        self.assertLess(failed_at-sample_sent,cfg['motion']['timeout'],
                                        'failure did not precede full motion timeout')
                    self.assertEqual(worker.wait(timeout=3),1)
                    self.assertEqual(server.recv(1),b'')
                    return
                if paused or foreign_peer:
                    self.assertEqual(json.loads(line(parent)),{'event':'failed'})
                    self.assertEqual(worker.wait(timeout=3),1)
                    self.assertEqual(server.recv(1),b'')
                    return
                received=json.loads(line(server));self.assertEqual(received['sample_sha256'],motion_digest(sample));self.assertEqual(received['status'],'accepted')
                sample=send_sample(2);received=json.loads(line(server));self.assertEqual(received['sample_sha256'],motion_digest(sample))
                control(2,'pause')
                if paused_after:
                    send_sample(3)
                    self.assertEqual(json.loads(line(parent)),{'event':'failed'})
                    self.assertEqual(worker.wait(timeout=3),1)
                    self.assertEqual(server.recv(1),b'')
                    return
                parent.sendall(b'{"command":"stop"}\n');self.assertEqual(json.loads(line(parent)),{'event':'stopped'})
                self.assertEqual(worker.wait(timeout=3),0);self.assertIsNone(lua.poll())
        finally:
            for sock in sockets:
                try:sock.close()
                except OSError:pass
            for child in reversed(children):
                if child.poll() is None:child.terminate()
                try:child.communicate(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.communicate(timeout=3)

    def test_resume_two_samples_pause_stop_on_one_tcp_owner(self):self.run_case()
    def test_foreign_motion_socket_peer_is_rejected(self):self.run_case(foreign_peer=True)
    def test_motion_before_resume_is_rejected(self):self.run_case(paused=True)
    def test_motion_after_pause_is_rejected(self):self.run_case(paused_after=True)
    def test_stop_while_local_binding_pending(self):self.run_case(stop_bound=True)
    def test_overall_deadline_fences_local_binding(self):self.run_case(deadline_bound=True)
    def test_fourth_fd_without_motion_config_refused(self):self.run_case(missing_config=True)
    def test_client_process_exit_after_active_is_fenced(self):self.run_case(identity_loss=True)

    def test_claim_attempt_cannot_be_motion_secret(self):
        epoch,attempt='9'*32,'7'*32
        receipt=Receipt(epoch,1,1,1,attempt,'checkpoint-'+'6'*32,'5'*64,10)
        cfg={'version':1,'claim':encode_load_claim(HonestClientLoadClaim(receipt,'4'*32,True,True)).decode(),
             'epoch':epoch,'handle':1,'lease':'8'*32,'udp_peer':['127.0.0.1',1234],
             'udp_next_id':1,'deadline':time.monotonic()+5,'controller_timeout':3,'client_process':ident(os.getpid()),
             'motion':{'lease':'a'*32,'attempt':'b'*32,'epoch':'c'*32,'generation':'d'*32,'timeout':1}}
        for key in ('lease','attempt'):
            bad={**cfg,'motion':{**cfg['motion'],key:attempt}}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'claim attempt'):
                worker_module.config_value(json.dumps(bad).encode())
        self.assertEqual(worker_module.config_value(json.dumps(cfg).encode())[0],cfg)

    def test_three_fds_with_motion_config_refused(self):
        from test_authority_tcp_native_worker import WorkerTest
        case=WorkerTest('test_wrong_ack_faults_before_udp_dispatch');case.setUp()
        try:
            case.cfg['motion']={'lease':'1'*32,'attempt':'2'*32,'epoch':'3'*32,'generation':'4'*32,'timeout':.2}
            case.config();case.event('failed');self.assertEqual(case.proc.wait(timeout=2),1)
            self.assertEqual(case.server.recv(1),b'')
        finally:case.doCleanups()

    def test_guard_interrupts_wait_for_ready(self):
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0))
        stopped=threading.Event();entered=threading.Event()
        cfg={'client_process':ident(os.getpid()),'motion':{'lease':'a'*32,'attempt':'b'*32,'epoch':'c'*32,'generation':'d'*32,'timeout':1}}
        def guard():
            if stopped.is_set():raise RuntimeError('parent stopped')
        motion=worker_module.LazyMotion(udp,cfg,guard);motion.running=True
        original=worker_module.ExperimentalParticipantMotionIPC.wait_ready
        def waiting(bridge):entered.set();return original(bridge)
        def stop():self.assertTrue(entered.wait(1));stopped.set()
        thread=threading.Thread(target=stop);thread.start()
        try:
            with patch.object(worker_module.ExperimentalParticipantMotionIPC,'wait_ready',waiting):
                with self.assertRaisesRegex(RuntimeError,'parent stopped'):motion({},False)
        finally:thread.join(2);motion.close()

    def test_duplicate_udp_fd_is_not_a_separate_socket_owner(self):
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);listener.bind(('127.0.0.1',0));listener.listen(1)
        tcp=socket.create_connection(listener.getsockname(),timeout=1);other,_=listener.accept()
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0))
        alias=socket.socket(fileno=os.dup(udp.fileno()));ipc,remote=socket.socketpair()
        try:
            with self.assertRaisesRegex(ValueError,'aliases'):
                worker_module.verify_sockets(tcp,udp,ipc,alias)
        finally:
            for item in (listener,tcp,other,udp,alias,ipc,remote):item.close()

if __name__=='__main__':unittest.main()
