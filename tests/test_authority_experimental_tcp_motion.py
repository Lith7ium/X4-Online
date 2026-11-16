"""Admitted TCP sockets with synthetic motion consumers; no X4 or setters."""
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
from authority.experimental_tcp_motion import ExperimentalTCPMotion, motion_value
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
import test_authority_experimental_tcp_participants as fixture

class Controller:
    def pause(self, handles):return True
    def resume(self, handles):return True

class MotionTCP(unittest.TestCase):
    def setUp(self):
        self.case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.stop=threading.Event();self.threads=[];self.errors=[];self.received=[]
        self.addCleanup(self.finish)
    def finish(self):
        self.stop.set()
        for thread in self.threads:thread.join(2)
        self.assertFalse(any(t.is_alive() for t in self.threads));self.assertEqual(self.errors,[])
    def client(self,conn,handle,*,failure=False,mutate=False):
        def run():
            try:
                conn.settimeout(3);frame=b''
                while not frame.endswith(b'\n'):
                    part=conn.recv(1)
                    if not part:raise RuntimeError('missing admission')
                    frame+=part
                assert json.loads(frame)['kind']=='accepted'
                def accept(value,despawn):
                    self.received.append((handle,dict(value),despawn))
                    if mutate:value['index']+=1
                    return not failure
                app=ExperimentalTCPParticipantClient(conn,Controller(),enabled=True,epoch='a'*32,handle=handle,
                                                     timeout=1,apply_motion=accept,apply_job=lambda x:True)
                while not self.stop.is_set():app.poll(.05)
                app.close()
            except BaseException as error:
                if not self.stop.is_set() and not failure and not mutate:self.errors.append(error)
        thread=threading.Thread(target=run);self.threads.append(thread);thread.start()
    def setup_pair(self,*,max_tracks=100000,min_interval=1/240,**kw):
        a=self.case.connect();b=self.case.connect();self.case.offer_and_claim(a);self.case.offer_and_claim(b)
        self.client(a,1);self.client(b,2,**kw);self.case.host.tick(.1)
        self.assertEqual(self.case.world.session.state,'running')
        self.delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        self.motion=ExperimentalTCPMotion(self.delivery,enabled=True,min_interval=min_interval,max_tracks=max_tracks)
        self.motion.track('b'*32,'c'*32,10055)
    @staticmethod
    def sample(seq=1,frame='sector_a',t=1,velocity=None):
        return {'version':1,'epoch':'b'*32,'generation':'c'*32,'index':10055,'sequence':seq,
                'sector_macro':frame,'source_time':t,'x':1,'y':2,'z':3,'velocity':velocity}
    def test_two_clients_shared_delivery_motion_transition_and_despawn(self):
        self.setup_pair();first=self.sample();self.assertTrue(self.motion.send(first))
        self.assertEqual(len(self.received),2)
        # Despawn itself is not rate limited and closes this lifetime.
        dead={k:first[k] for k in ('version','epoch','generation','index','sequence')};dead['sequence']=2
        self.assertTrue(self.motion.send(dead,despawn=True));self.assertEqual(len(self.received),4)
        with self.assertRaises(ValueError):self.motion.send(self.sample(3))
        self.assertTrue(self.case.host._failed)
    def test_stale_or_wrong_transition_fences_sender(self):
        self.setup_pair();first=self.sample();self.assertTrue(self.motion.send(first))
        with self.assertRaises(ValueError):self.motion.send(self.sample(2,'sector_b',2,{'x':1,'y':0,'z':0}))
        self.assertTrue(self.case.host._failed)
    def test_motion_and_job_share_owner_and_frame_change_resets_velocity(self):
        self.setup_pair();self.assertTrue(self.motion.send(self.sample()))
        job={'epoch':'b'*32,'generation':'d'*32,'sequence':1,'index':10055,
             'descriptor':{'macro':'ship_a','faction':'argon','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        self.assertTrue(self.delivery.deliver(job,self.delivery.membership(),lambda *_:True))
        time.sleep(.01)
        self.assertTrue(self.motion.send(self.sample(2,'sector_b',2)))
        self.assertEqual([v[1]['sector_macro'] for v in self.received],['sector_a','sector_a','sector_b','sector_b'])
    def test_failed_consumer_fences_host_after_partial_delivery(self):
        self.setup_pair(failure=True)
        with self.assertRaises((RuntimeError,ValueError,ConnectionError,OSError)):
            self.motion.send(self.sample())
        self.assertTrue(self.case.host._failed);self.assertEqual([v[0] for v in self.received],[1,2])
    def test_mutation_is_not_acknowledged(self):
        self.setup_pair(mutate=True)
        with self.assertRaises((RuntimeError,ValueError,ConnectionError,OSError)):
            self.motion.send(self.sample())
        self.assertTrue(self.case.host._failed)
    def test_invalid_values_and_no_fake_velocity(self):
        value=self.sample();self.assertIsNone(motion_value(value)['velocity'])
        for changed in ({'x':float('nan')},{'sequence':True},{'velocity':{'x':5001,'y':0,'z':0}},
                        {'sector_macro':'bad sector'},{'index':2**53}):
            with self.assertRaises(ValueError):motion_value({**value,**changed})
    def test_lifetime_capacity_exhaustion_fences_owner(self):
        self.setup_pair(max_tracks=1)
        with self.assertRaises(ValueError):self.motion.track('b'*32,'d'*32,10056)
        self.assertTrue(self.case.host._failed)
    def test_rate_limit_rejects_without_sending_or_faulting(self):
        self.setup_pair(min_interval=10);self.assertTrue(self.motion.send(self.sample()))
        with self.assertRaises(ValueError):self.motion.send(self.sample(2,t=2))
        self.assertEqual(len(self.received),2);self.assertFalse(self.case.host._failed)

if __name__=='__main__':unittest.main()
