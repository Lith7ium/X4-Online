"""Saved source and client through real UDP/TCP; X4 ABI and MD are simulated."""
import json
import os
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests'), str(ROOT/'tools/dev')]
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
from authority_tcp_native_worker import check_process
from authority_source_job_bind import bind_source
from authority_tcp_job_client_live import socket_owner
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
import test_authority_experimental_tcp_participants as fixture


class Controller:
    def __init__(self): self.operations = []
    def pause(self, _): self.operations.append('pause'); return True
    def resume(self, _): self.operations.append('resume'); return True


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('cc') and shutil.which('luajit'),
                     'Linux, LuaJIT and a C compiler required')
class SavedMotionPairLifecycle(unittest.TestCase):
    def test_two_saved_samples_then_join_pauses_and_saves(self):
        case = fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        case.setUp()
        stop, ready, errors = threading.Event(), threading.Event(), []
        proc = source_proc = thread = sock = source_sock = source_bridge = None
        cleanup_errors=[];err=source_err=b''
        controller = Controller()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                net, abi, source_abi = Path(tmp)/'net.so', Path(tmp)/'abi.so', Path(tmp)/'source_abi.so'
                subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(net)],cwd=ROOT,check=True,capture_output=True)
                subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/replica_motion_binding_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
                subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/multi_create_running_owner_abi.c','-o',str(source_abi)],cwd=ROOT,check=True,capture_output=True)
                client = case.connect(); case.offer_and_claim(client)
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.bind(('127.0.0.1',0))
                env = dict(os.environ, LD_PRELOAD=str(abi), TEST_NET_LIB=str(net), TEST_NET_PORT=str(sock.getsockname()[1]))
                proc = subprocess.Popen(['luajit','tests/authority_saved_motion_pair_client_fake_x4.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                image = os.stat(f'/proc/{proc.pid}/exe')
                fields = Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()
                identity = {'pid':proc.pid, 'start_ticks':int(fields[19]), 'exe_dev':image.st_dev, 'exe_ino':image.st_ino}
                source_sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);source_sock.bind(('127.0.0.1',0))
                source_env=dict(os.environ,LD_PRELOAD=str(source_abi),TEST_NET_LIB=str(net),TEST_NET_PORT=str(source_sock.getsockname()[1]))
                source_proc=subprocess.Popen(['luajit','tests/authority_source_saved_pair_fake_x4.lua'],cwd=ROOT,env=source_env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                image=os.stat(f'/proc/{source_proc.pid}/exe')
                fields=Path(f'/proc/{source_proc.pid}/stat').read_text().rsplit(')',1)[1].split()
                source_identity={'pid':source_proc.pid,'start_ticks':int(fields[19]),'exe_dev':image.st_dev,'exe_ino':image.st_ino}
                def owner_alive():
                    self.assertIsNone(proc.poll(), 'saved motion owner exited')
                    check_process(identity)
                    self.assertIsNone(source_proc.poll(), 'saved source owner exited')
                    check_process(source_identity)
                    self.assertTrue(thread.is_alive(), 'participant TCP owner exited')
                    self.assertEqual(errors, [])
                def participant():
                    bridge = adapter = None
                    try:
                        client.settimeout(3); frame=b''
                        while not frame.endswith(b'\n'):
                            block=client.recv(1)
                            if not block: raise RuntimeError('admission ended')
                            frame += block
                        if json.loads(frame)['kind'] != 'accepted': raise ValueError('admission refused')
                        destination=sock.getsockname()
                        bridge=ExperimentalParticipantMotionIPC(sock,enabled=True,lease='a'*32,attempt='b'*32,epoch='c'*32,generation='d'*32,
                            guard=lambda:proc.poll() is None,validate_peer=lambda p:socket_owner(p,destination,identity),timeout=2)
                        bridge.wait_ready()
                        adapter=ExperimentalTCPParticipantClient(client,controller,enabled=True,epoch='a'*32,handle=1,timeout=3,apply_motion=bridge)
                        ready.set()
                        while not stop.is_set(): adapter.poll(.05)
                    except BaseException as error:
                        if not stop.is_set(): errors.append(error)
                    finally:
                        for owned in (adapter,bridge):
                            try:
                                if owned is adapter and owned and not owned._closed and not owned._failed: owned.close()
                                if owned is bridge and owned and owned.state not in ('closed','failed'): owned.close()
                            except BaseException as error: errors.append(error)
                thread=threading.Thread(target=participant); thread.start()
                case.host.tick(.1)
                self.assertTrue(ready.wait(3))
                self.assertEqual(case.world.session.state, 'running')
                owner_alive()
                self.assertTrue(select.select([source_proc.stdout],[],[],3)[0], 'missing paused source receipt')
                self.assertEqual(source_proc.stdout.readline(),b'PAUSED\n')
                destination=source_sock.getsockname()
                source_sock=bind_source(source_sock,process=source_identity,lease='1'*32,attempt='2'*32,epoch='c'*32,generation='d'*32,
                    guard=lambda:source_proc.poll() is None,timeout=3)
                # This pipe is a test-only stand-in for the separate game-control
                # resume. The source motion IPC itself does not support GO.
                source_proc.stdin.write(b'GO\n');source_proc.stdin.flush()
                self.assertTrue(select.select([source_proc.stdout],[],[],3)[0], 'missing running source receipt')
                self.assertEqual(source_proc.stdout.readline(),b'RUNNING\n')
                delivery=ExperimentalTCPJobDelivery(case.host,enabled=True,timeout=3)
                motion=ExperimentalTCPMotion(delivery,enabled=True)
                source_bridge=ExperimentalSourceMotionIPC(source_sock,motion,enabled=True,lease='1'*32,attempt='2'*32,epoch='c'*32,generation='d'*32,
                    guard=lambda:source_proc.poll() is None,validate_peer=lambda peer:socket_owner(peer,destination,source_identity),timeout=4,
                    saved_baseline=10054,saved_guard=lambda epoch,baseline:epoch=='c'*32 and baseline==10054)
                self.assertTrue(source_bridge.register_saved(42))
                first=source_bridge.pull()
                self.assertEqual((first['index'],first['sequence'],first['velocity']),(42,1,None))
                deadline=time.monotonic()+1/60
                while time.monotonic()<deadline: time.sleep(max(0,deadline-time.monotonic()))
                second=None
                deadline=time.monotonic()+2
                while second is None and time.monotonic()<deadline:
                    second=source_bridge.pull()
                self.assertIsNotNone(second, 'no second saved sample before deadline')
                self.assertEqual((second['index'],second['sequence'],second['velocity']),(42,2,{'x':2,'y':0,'z':0}))
                source_bridge.close();source_bridge=None;source_sock=None
                # No competing TCP reader is introduced: the same adapter then
                # processes a real participant pause for a joining connection.
                owner_alive(); joining=case.connect()
                case.host.tick(.1)
                self.assertEqual(case.world.session.state,'saving')
                self.assertEqual(controller.operations,['resume','pause'])
                owner_alive()
                case.host.tick(.1)
                self.assertEqual(case.world.session.state,'paused')
                self.assertEqual(case.engine.calls,['pause','save','resume','pause','save'])
                owner_alive()
                joining.close()
        finally:
            stop.set()
            def clean(action):
                try: action()
                except BaseException as error: cleanup_errors.append(error)
            if thread:
                clean(lambda:thread.join(3))
                if thread.is_alive(): cleanup_errors.append(RuntimeError('participant TCP owner still alive'))
            def reap(child):
                if child.poll() is None: child.terminate()
                try: return child.communicate(timeout=3)[1]
                except BaseException:
                    if child.poll() is None: child.kill()
                    child.communicate(timeout=3)
                    raise
            if proc:
                try: err=reap(proc)
                except BaseException as error: cleanup_errors.append(error)
            if sock: clean(sock.close)
            if source_bridge and source_bridge.state not in ('closed','failed'): clean(source_bridge.close)
            if source_sock: clean(source_sock.close)
            if source_proc:
                try: source_err=reap(source_proc)
                except BaseException as error: cleanup_errors.append(error)
            clean(case.doCleanups)
            if cleanup_errors: raise BaseExceptionGroup('owned test cleanup failed',cleanup_errors)
        self.assertFalse(thread and thread.is_alive())
        self.assertEqual(errors,[])
        self.assertEqual(err,b'')
        self.assertEqual(source_err,b'')

if __name__ == '__main__': unittest.main()
