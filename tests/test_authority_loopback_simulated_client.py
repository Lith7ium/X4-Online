"""Loopback probe against fake X4; no game is started and client events are synthetic."""
import gzip
import importlib.util
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('authority_loopback_simulated_client',ROOT/'tools/dev/authority_loopback_simulated_client.py')
PROBE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(PROBE)
from authority.checkpoints import CheckpointStore
from authority.experimental_local_host import ExperimentalLocalHost
from authority.experimental_tcp_control import ExperimentalTCPControl
from authority.experimental_tcp_participants import ExperimentalTCPParticipants
from authority.save_transfer import SaveOffers
from authority.trusted_marker_load_session import TrustedMarkerLoadSession
from authority.world import WorldCoordinator
from lockstep.launcher.joinfiles import FileService
from test_authority_trusted_marker_load_session import XML, MARKER


class Engine:
    def __init__(self,root): self.root=root; self.count=0; self.pending_marker=None; self.calls=[]
    def pause(self): self.calls.append('pause')
    def resume(self): self.calls.append('resume')
    def save(self):
        self.calls.append('save'); self.count+=1; self.pending_marker=('%032x'%self.count)
        path=self.root/'engine-save.gz'; path.write_bytes(gzip.compress(XML.replace(MARKER,self.pending_marker).encode()))
        return path


class ProbeTests(unittest.TestCase):
    def test_two_real_transfers_and_synthetic_client_events(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'store').mkdir(); (root/'out').mkdir()
            ready=threading.Event(); stop=threading.Event(); errors=[]; shared={}
            def server():
                service=control=listener=None
                try:
                    store=CheckpointStore(root/'store'); engine=Engine(root)
                    service=FileService('a'*32,slots=(1,)).start()
                    world=WorldCoordinator('a'*32,engine,store,SaveOffers(service,store))
                    control=ExperimentalTCPControl(TrustedMarkerLoadSession(world,enabled=True),enabled=True,
                                                   keepalive_enabled=True)
                    host=ExperimentalLocalHost(world,control,service,enabled=True)
                    world._participants=ExperimentalTCPParticipants(host,enabled=True,timeout=2)
                    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);listener.bind(('127.0.0.1',0))
                    listener.listen(4);listener.setblocking(False)
                    shared.update(config={'control_host':'127.0.0.1','control_port':listener.getsockname()[1],
                        'file_host':'127.0.0.1','file_port':service.port,'file_token':'a'*32}, engine=engine)
                    ready.set()
                    while not stop.is_set():
                        try: conn,_=listener.accept()
                        except BlockingIOError: pass
                        else: host.adopt(conn)
                        host.tick(.01)
                        if not control._peers: time.sleep(.002)
                except BaseException as error: errors.append(error);ready.set()
                finally:
                    if control is not None and not (control._closed or control._failed): control.close()
                    if listener is not None: listener.close()
                    if service is not None: service.close();service.thread.join(2)
            thread=threading.Thread(target=server);thread.start()
            try:
                self.assertTrue(ready.wait(2)); self.assertFalse(errors)
                result=PROBE.run(shared['config'],root/'out',count=2,timeout=10)
                self.assertTrue(result['success']); self.assertTrue(result['client_x4_load_simulated'])
                first,second=result['attempts']
                self.assertNotEqual(first['checkpoint_id'],second['checkpoint_id'])
                self.assertNotEqual(first['marker'],second['marker'])
                self.assertTrue(all(row['transfer_verified'] for row in result['attempts']))
                self.assertTrue(all(row['participant_controls_simulated'] for row in result['attempts']))
                deadline=time.monotonic()+3
                while shared['engine'].count<3 and time.monotonic()<deadline: time.sleep(.01)
                self.assertEqual(shared['engine'].count,3)
                self.assertFalse(errors)
            finally:
                stop.set();thread.join(3)
            self.assertFalse(thread.is_alive());self.assertFalse(errors)


if __name__=='__main__': unittest.main()
