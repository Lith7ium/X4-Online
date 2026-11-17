"""Admitted TCP and saved client binding with real UDP, simulated X4 and MD."""
import json
import os
from pathlib import Path
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
from authority.experimental_tcp_motion import ExperimentalTCPMotion, motion_digest
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
from authority_tcp_native_worker import check_process
import test_authority_experimental_tcp_participants as fixture


class Controller:
    def __init__(self): self.operations = []
    def pause(self, _): self.operations.append('pause'); return True
    def resume(self, _): self.operations.append('resume'); return True


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('cc') and shutil.which('luajit'),
                     'Linux, LuaJIT and a C compiler required')
class SavedMotionLifecycle(unittest.TestCase):
    def test_two_saved_samples_then_join_pauses_and_saves(self):
        self.exercise_saved_motion(first_pair_sample_only=False)

    def test_second_pair_sample_is_accepted_as_first_client_sample(self):
        self.exercise_saved_motion(first_pair_sample_only=True)

    def exercise_saved_motion(self, *, first_pair_sample_only):
        case = fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        case.setUp()
        stop, ready, errors = threading.Event(), threading.Event(), []
        proc = thread = sock = None
        controller = Controller()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                net, abi = Path(tmp)/'net.so', Path(tmp)/'abi.so'
                subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(net)],cwd=ROOT,check=True,capture_output=True)
                subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/replica_motion_binding_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
                client = case.connect(); case.offer_and_claim(client)
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.bind(('127.0.0.1',0))
                env = dict(os.environ, LD_PRELOAD=str(abi), TEST_NET_LIB=str(net), TEST_NET_PORT=str(sock.getsockname()[1]))
                proc = subprocess.Popen(['luajit','tests/authority_saved_motion_tcp_lua_fake_x4.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                image = os.stat(f'/proc/{proc.pid}/exe')
                fields = Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()
                identity = {'pid':proc.pid, 'start_ticks':int(fields[19]), 'exe_dev':image.st_dev, 'exe_ino':image.st_ino}
                def owner_alive():
                    self.assertIsNone(proc.poll(), 'saved motion owner exited')
                    check_process(identity)
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
                        bridge=ExperimentalParticipantMotionIPC(sock,enabled=True,lease='a'*32,attempt='b'*32,epoch='c'*32,generation='d'*32,
                            guard=lambda:proc.poll() is None,validate_peer=lambda p:p[0]=='127.0.0.1',timeout=2)
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
                delivery=ExperimentalTCPJobDelivery(case.host,enabled=True,timeout=3)
                motion=ExperimentalTCPMotion(delivery,enabled=True);motion.track('c'*32,'d'*32,42)
                first={'version':1,'epoch':'c'*32,'generation':'d'*32,'index':42,'sequence':1,'sector_macro':'sector_a',
                    'source_time':1,'x':1,'y':2,'z':3,'velocity':None}
                second={**first,'sequence':2,'source_time':1.5,'x':2,'velocity':{'x':2,'y':0,'z':0}}
                if not first_pair_sample_only:
                    self.assertTrue(motion.send(first))
                    deadline=time.monotonic()+1/60
                    while time.monotonic()<deadline:
                        time.sleep(max(0,deadline-time.monotonic()))
                self.assertTrue(motion.send(second))
                if first_pair_sample_only:
                    track = motion._tracks[('c'*32, 'd'*32, 42)]
                    self.assertIn((2, motion_digest(second)), track['peer_samples'].values())
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
            if thread: thread.join(3)
            if proc:
                if proc.poll() is None: proc.terminate()
                _,err=proc.communicate(timeout=3)
            else: err=b''
            if sock: sock.close()
            case.doCleanups()
        self.assertFalse(thread and thread.is_alive())
        self.assertEqual(errors,[])
        self.assertEqual(err,b'')

if __name__ == '__main__': unittest.main()
