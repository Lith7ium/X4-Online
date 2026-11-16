"""Real loopback sockets and synthetic participants; no game or WAN."""
from pathlib import Path
import socket
import sys
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import test_authority_experimental_tcp_motion as motion_fixture


class LatestMotionPollTest(unittest.TestCase):
    def setUp(self):
        self.case=motion_fixture.MotionTCP('test_two_clients_shared_delivery_motion_transition_and_despawn')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.case.setup_pair(delay=.35)
        self.host=self.case.case.host;self.control=self.case.case.control
        self.control.enable_latest_motion(enabled=True,timeout=1,per_peer_limit=2)
        self.motion=self.case.motion

    def spin(self,predicate,timeout=2):
        end=time.monotonic()+timeout
        while not predicate() and time.monotonic()<end:self.host.tick(.01)
        self.assertTrue(predicate())

    def test_slow_peer_does_not_stop_fast_peer_and_latest_replaces_pending(self):
        self.motion.enqueue_latest(self.case.sample())
        self.spin(lambda:len(self.case.received)>=2)
        self.motion.enqueue_latest(self.case.sample(2,t=2))
        self.motion.enqueue_latest(self.case.sample(3,t=3))
        self.spin(lambda:any(h==1 and s['sequence']==3 for h,s,_ in self.case.received),timeout=.25)
        self.spin(lambda:any(h==2 and s['sequence']==3 for h,s,_ in self.case.received))
        by_peer={h:[s['sequence'] for who,s,_ in self.case.received if who==h] for h in (1,2)}
        self.assertEqual(by_peer[2],[1,3]);self.assertNotIn(2,by_peer[1])
        self.spin(lambda:self.control._motion_idle())

    def test_partially_sent_frame_is_completed_before_newer_sample(self):
        peers=list(self.control._peers);target=peers[0];original=socket.socket.send;once=[False]
        def short(sock,data,*args,**kwargs):
            if sock is target and not once[0]:once[0]=True;data=data[:7]
            return original(sock,data,*args,**kwargs)
        self.motion.enqueue_latest(self.case.sample())
        with patch.object(socket.socket,'send',short): self.host.tick(.01)
        self.assertTrue(once[0]);self.motion.enqueue_latest(self.case.sample(2,t=2))
        self.spin(lambda:any(h==1 and s['sequence']==2 for h,s,_ in self.case.received))
        self.assertEqual([s['sequence'] for h,s,_ in self.case.received if h==1],[1,2])
        self.spin(lambda:self.control._motion_idle())

    def test_lifecycle_barrier_discards_pending_and_waits_for_sent_receipt(self):
        self.motion.enqueue_latest(self.case.sample());self.spin(lambda:len(self.case.received)>=2)
        self.motion.enqueue_latest(self.case.sample(2,t=2))
        self.assertFalse(self.control.motion_barrier())
        with self.assertRaises(RuntimeError):self.motion.enqueue_latest(self.case.sample(3,t=3))
        self.spin(lambda:self.control.motion_barrier())
        self.assertFalse(any(s['sequence']==2 for _,s,_ in self.case.received))
        self.control.release_motion_barrier()
        self.motion.enqueue_latest(self.case.sample(3,t=3));self.spin(lambda:self.control._motion_idle())

    def test_join_waits_for_inflight_before_pause_and_discards_pending(self):
        self.motion.enqueue_latest(self.case.sample());self.spin(lambda:len(self.case.received)>=2)
        self.motion.enqueue_latest(self.case.sample(2,t=2))
        third=self.case.case.connect()
        self.host.tick(0)
        self.assertEqual(self.case.case.world.session.state,'pausing')
        self.assertNotIn('pause',self.case.case.engine.calls[3:])
        self.spin(lambda:self.case.case.world.session.state!='pausing')
        self.assertIn('pause',self.case.case.engine.calls[3:])
        self.assertFalse(any(s['sequence']==2 for _,s,_ in self.case.received))
        third.close()

    def test_slow_timeout_disconnects_only_that_peer(self):
        self.control._latest_motion.timeout=.15
        self.motion.enqueue_latest(self.case.sample())
        self.spin(lambda:len(self.control._peers)==1,timeout=1)
        self.assertEqual(self.case.case.world.session.state,'running')
        self.motion.enqueue_latest(self.case.sample(2,t=2))
        self.spin(lambda:any(h==1 and s['sequence']==2 for h,s,_ in self.case.received),timeout=.15)
        self.case.stop.set()

    def test_mismatched_receipt_disconnects_only_that_peer(self):
        target=list(self.control._peers)[1];original=socket.socket.recv
        def corrupt(sock,size,*args,**kwargs):
            data=original(sock,size,*args,**kwargs)
            if sock is target and data and not args and not kwargs:return b'{}\n'
            return data
        self.motion.enqueue_latest(self.case.sample())
        with patch.object(socket.socket,'recv',corrupt):
            self.spin(lambda:len(self.control._peers)==1)
        self.assertEqual(self.case.case.world.session.state,'running')
        self.motion.enqueue_latest(self.case.sample(2,t=2))
        self.spin(lambda:any(h==1 and s['sequence']==2 for h,s,_ in self.case.received))
        self.case.stop.set()

    def test_discard_of_never_sent_frame_does_not_reserve_old_sector(self):
        self.motion.enqueue_latest(self.case.sample())
        self.assertTrue(self.control.motion_barrier())
        self.control.release_motion_barrier()
        self.motion.enqueue_latest(self.case.sample(2,frame='sector_b',t=2))
        self.spin(lambda:self.control._motion_idle())
        self.assertEqual({s['sector_macro'] for _,s,_ in self.case.received},{'sector_b'})

    def test_job_delivery_requires_drained_explicit_barrier(self):
        self.motion.enqueue_latest(self.case.sample());self.spin(lambda:len(self.case.received)>=2)
        members=self.case.delivery.membership()
        event={'epoch':'b'*32,'generation':'d'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_a','faction':'argon','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        with self.assertRaises(RuntimeError):
            self.case.delivery.deliver(event,members,lambda *_:True)
        self.assertFalse(self.host._failed)
        self.spin(lambda:self.control.motion_barrier())
        self.assertTrue(self.case.delivery.deliver(event,members,lambda *_:True))
        self.control.release_motion_barrier()

    def test_gate_flush_without_barrier_faults_after_gate_dispatch(self):
        self.motion.enqueue_latest(self.case.sample())
        members=self.case.delivery.membership()
        event={'epoch':'b'*32,'generation':'d'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_a','faction':'argon','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        for member in members:self.case.delivery.enqueue(member,event)
        with self.assertRaises(RuntimeError):self.case.delivery.flush(lambda *_:True)
        self.assertTrue(self.host._failed)

    def test_other_socket_owners_cannot_take_pending_motion_reader(self):
        self.motion.enqueue_latest(self.case.sample())
        with self.assertRaises(RuntimeError):self.control._reader_free()
        self.assertFalse(self.host._failed)
        self.assertTrue(self.control.motion_barrier())
        self.control._reader_free()

    def test_current_source_lease_can_queue_without_a_second_reader(self):
        self.motion._source_owner=object();lease=object();self.motion._source_lease=lease
        self.motion.enqueue_latest(self.case.sample(),_source=lease)
        self.spin(lambda:self.control._motion_idle())
        self.assertEqual(len(self.case.received),2)
