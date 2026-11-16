"""Real admitted TCP and local UDP sockets; X4 owners are synthetic."""
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
import test_authority_experimental_tcp_participants as fixture

class Controller:
    def pause(self,handles):return True
    def resume(self,handles):return True

def udp():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',0));return s

class Integration(unittest.TestCase):
    def setUp(self):
        self.case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.stop=threading.Event();self.threads=[];self.errors=[];self.bound=[]
        self.addCleanup(self.finish)
    def finish(self):
        self.stop.set()
        for t in self.threads:t.join(3)
        self.assertFalse(any(t.is_alive() for t in self.threads));self.assertEqual(self.errors,[])
    def start(self,fn):
        t=threading.Thread(target=fn);self.threads.append(t);t.start()
    def run_bridge(self,validate_sample=None):
        tcp=self.case.connect();self.case.offer_and_claim(tcp)
        client_udp,x4_udp=udp(),udp();self.addCleanup(client_udp.close);self.addCleanup(x4_udp.close)
        src_udp,x4_src=udp(),udp();self.addCleanup(src_udp.close);self.addCleanup(x4_src.close)
        src_udp.connect(x4_src.getsockname());x4_src.connect(src_udp.getsockname())
        L,A,E,G='1'*32,'2'*32,'b'*32,'c'*32
        peer_ready=threading.Event()
        def fake_client_x4():
            try:
                x4_udp.settimeout(.1)
                x4_udp.sendto(f'R|{L}|{A}|READY|{E}|{G}'.encode(),client_udp.getsockname())
                while not self.stop.is_set():
                    try:data,peer=x4_udp.recvfrom(769)
                    except socket.timeout:continue
                    parts=data.decode().split('|');assert parts[:4]==['M',L,A,'BIND']
                    time.sleep(.05);self.bound.append(parts[4:])
                    x4_udp.sendto('|'.join(['R',L,A,'BOUND',*parts[4:11]]).encode(),peer)
            except BaseException as e:
                if not self.stop.is_set():self.errors.append(e)
        def participant():
            try:
                tcp.settimeout(3);frame=b''
                while not frame.endswith(b'\n'):frame+=tcp.recv(1)
                assert json.loads(frame)['kind']=='accepted'
                bridge=ExperimentalParticipantMotionIPC(client_udp,enabled=True,lease=L,attempt=A,epoch=E,generation=G,
                    guard=lambda:True,validate_peer=lambda p:p==x4_udp.getsockname(),timeout=1)
                bridge.wait_ready();peer_ready.set()
                adapter=ExperimentalTCPParticipantClient(tcp,Controller(),enabled=True,epoch='a'*32,handle=1,
                                                          timeout=2,apply_motion=bridge)
                while not self.stop.is_set():adapter.poll(.05)
                adapter.close();bridge.close()
            except BaseException as e:
                if not self.stop.is_set():self.errors.append(e)
        def source_x4():
            try:
                x4_src.settimeout(.1);count=0
                while not self.stop.is_set():
                    try:data=x4_src.recv(769)
                    except socket.timeout:continue
                    parts=data.decode().split('|');assert parts[:6]==['P','3'*32,'4'*32,'PULL',E,G]
                    count+=1;response=['S','3'*32,'4'*32]
                    if count==1:response+=['SAMPLE',E,G,parts[6],'10055','1','sector_a','10','1','2','3','-','-','-']
                    else:response+=['NO_SAMPLE',E,G,parts[6]]
                    x4_src.send('|'.join(response).encode())
            except BaseException as e:
                if not self.stop.is_set():self.errors.append(e)
        self.start(fake_client_x4);self.start(participant);self.start(source_x4)
        self.case.host.tick(.1);self.assertTrue(peer_ready.wait(3))
        delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        motion=ExperimentalTCPMotion(delivery,enabled=True)
        source=ExperimentalSourceMotionIPC(src_udp,motion,enabled=True,lease='3'*32,attempt='4'*32,
                 epoch=E,generation=G,guard=lambda:True,validate_peer=lambda p:p==x4_src.getsockname(),timeout=3,
                 validate_sample=validate_sample)
        source.bind_confirmed(10055)
        if validate_sample is not None:
            with self.assertRaises(ValueError):source.pull()
            self.assertEqual(self.bound,[]);return
        before=time.monotonic();result=source.pull();after=time.monotonic()
        self.assertGreaterEqual(after-before,.04);self.assertEqual(len(self.bound),1)
        self.assertEqual((result['index'],result['sequence'],result['velocity']),(10055,1,None))
        self.assertIsNone(source.pull());source.close()

    def test_real_tcp_and_udp_wait_for_correlated_readback(self):self.run_bridge()
    def test_mutated_validator_copy_fails_before_tcp(self):
        def mutate(value):value['x']=int(value['x']);return True
        self.run_bridge(mutate)

if __name__=='__main__':unittest.main()
