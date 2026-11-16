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
    def client(self,conn,handle,*,failure=False,mutate=False,delay=0):
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
                    if delay:time.sleep(delay)
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
    def test_explicit_subset_then_other_client_and_default_all(self):
        self.setup_pair();members=self.delivery.membership()
        self.assertTrue(self.motion.send(self.sample(),recipients=[members[0]]))
        self.assertEqual([item[0] for item in self.received],[1])
        time.sleep(.01)
        self.assertTrue(self.motion.send(self.sample(2,t=2),recipients=[members[1]]))
        self.assertEqual([item[0] for item in self.received],[1,2])
        time.sleep(.01)
        self.assertTrue(self.motion.send(self.sample(3,t=3)))
        self.assertEqual([item[0] for item in self.received],[1,2,1,2])
        self.assertEqual([item[1]['sequence'] for item in self.received],[1,2,3,3])
    def invalid_recipients(self,kind):
        self.setup_pair();members=self.delivery.membership()
        if kind=='duplicate':selected=[members[0],dict(members[0])]
        elif kind=='old':selected=[{**members[0],'incarnation':'0'*32}]
        elif kind=='foreign':selected=[{'id':'peer_999','incarnation':members[0]['incarnation']}]
        elif kind=='empty':selected=[]
        else:selected=[{**members[0],'extra':1}]
        with self.assertRaises(ValueError):self.motion.send(self.sample(),recipients=selected)
        self.assertEqual(self.received,[]);self.assertTrue(self.case.host._failed)
    def test_duplicate_recipient_fences(self):self.invalid_recipients('duplicate')
    def test_old_incarnation_fences(self):self.invalid_recipients('old')
    def test_foreign_recipient_fences(self):self.invalid_recipients('foreign')
    def test_empty_recipients_fence(self):self.invalid_recipients('empty')
    def test_malformed_recipient_fences(self):self.invalid_recipients('malformed')
    def test_incarnation_change_in_guard_fences_before_send(self):
        self.setup_pair();members=self.delivery.membership()
        def changed():self.delivery._incarnations[1]='0'*32;return True
        with self.assertRaises(RuntimeError):self.motion.send(self.sample(),recipients=[members[0]],guard=changed)
        self.assertEqual(self.received,[]);self.assertTrue(self.case.host._failed)
    def test_stale_or_wrong_transition_fences_sender(self):
        self.setup_pair();first=self.sample();self.assertTrue(self.motion.send(first))
        with self.assertRaises(ValueError):self.motion.send(self.sample(2,'sector_b',2,{'x':1,'y':0,'z':0}))
        self.assertTrue(self.case.host._failed)
    def test_motion_and_job_share_owner_and_frame_change_requires_resync(self):
        self.setup_pair();self.assertTrue(self.motion.send(self.sample()))
        job={'epoch':'b'*32,'generation':'d'*32,'sequence':1,'index':10055,
             'descriptor':{'macro':'ship_a','faction':'argon','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        self.assertTrue(self.delivery.deliver(job,self.delivery.membership(),lambda *_:True))
        time.sleep(.01)
        with self.assertRaises(ValueError):self.motion.send(self.sample(2,'sector_b',2))
        self.assertEqual([v[1]['sector_macro'] for v in self.received],['sector_a','sector_a'])
        self.assertTrue(self.case.host._failed)
    def recipient_frame_change_fails_before_send(self,velocity):
        self.setup_pair();members=self.delivery.membership()
        self.assertTrue(self.motion.send(self.sample(),recipients=[members[0]]));time.sleep(.01)
        self.assertTrue(self.motion.send(self.sample(2,'sector_b',2),recipients=[members[1]]));time.sleep(.01)
        with self.assertRaises(ValueError):self.motion.send(self.sample(3,'sector_b',3,velocity),recipients=[members[0]])
        self.assertEqual([(r[0],r[1]['sector_macro']) for r in self.received],[(1,'sector_a'),(2,'sector_b')])
        self.assertTrue(self.case.host._failed)
    def test_reentry_changed_frame_with_unknown_rate_fails(self):self.recipient_frame_change_fails_before_send(None)
    def test_reentry_changed_frame_with_known_rate_fails(self):self.recipient_frame_change_fails_before_send({'x':1,'y':0,'z':0})
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
    def test_process_guard_is_checked_while_waiting_for_readback(self):
        self.setup_pair(delay=.4);started=time.monotonic()
        with self.assertRaises(RuntimeError):
            self.motion.send(self.sample(),guard=lambda:time.monotonic()-started<.12)
        self.assertLess(time.monotonic()-started,.35);self.assertTrue(self.case.host._failed)

if __name__=='__main__':unittest.main()
