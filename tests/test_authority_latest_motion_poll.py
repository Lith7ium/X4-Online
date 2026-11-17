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

    def test_replacing_pending_sample_discards_it_once(self):
        self.motion.enqueue_latest(self.case.sample())
        self.spin(lambda: len(self.case.received) >= 2)
        member = [item for item in self.case.delivery.membership()
                  if item['id'] == 'peer_2']
        target = list(self.control._peers)[1]
        peer = self.control._peers[target]
        self.assertGreater(peer['motion_active']['sent'], 0)

        self.motion.enqueue_latest(self.case.sample(2, t=2), recipients=member)
        key = ('b' * 32, 'c' * 32, 10055)
        data, expected, accepted, discard, guard = peer['motion_pending'][key]
        discarded = []

        def record_discard():
            discarded.append(expected['request_id'])
            discard()

        peer['motion_pending'][key] = (data, expected, accepted, record_discard, guard)
        self.motion.enqueue_latest(self.case.sample(3, t=3), recipients=member)
        self.assertEqual(discarded, [2])
        self.assertIsNone(self.control._reader_lease)
        other_member = [item for item in self.case.delivery.membership()
                        if item['id'] == 'peer_1']
        self.motion.enqueue_latest(self.case.sample(4, t=4), recipients=other_member)
        self.spin(lambda: any(handle == 1 and sample['sequence'] == 4
                              for handle, sample, _ in self.case.received), timeout=.25)
        self.spin(lambda: self.control._motion_idle())
        self.assertEqual(discarded, [2])
        self.assertEqual([sample['sequence'] for handle, sample, _ in self.case.received
                          if handle == 2], [1, 3])

    def test_pending_replacement_preserves_track_order(self):
        member = [item for item in self.case.delivery.membership()
                  if item['id'] == 'peer_2']
        self.motion.enqueue_latest(self.case.sample(), recipients=member)
        self.spin(lambda: any(handle == 2 for handle, _, _ in self.case.received))
        self.motion.track('b' * 32, 'c' * 32, 10056)
        self.motion.track('b' * 32, 'c' * 32, 10057)
        first = self.case.sample()
        first['index'] = 10056
        second = self.case.sample()
        second['index'] = 10057
        self.motion.enqueue_latest(first, recipients=member)
        self.motion.enqueue_latest(second, recipients=member)
        replacement = self.case.sample(2, t=2)
        replacement['index'] = 10056
        self.motion.enqueue_latest(replacement, recipients=member)
        self.spin(self.control._motion_idle, timeout=3)
        self.assertEqual([(sample['index'], sample['sequence'])
                          for handle, sample, _ in self.case.received if handle == 2],
                         [(10055, 1), (10056, 2), (10057, 1)])

    def test_pending_discard_failure_fences_control_after_prior_peer_mutation(self):
        self.motion.enqueue_latest(self.case.sample())
        self.spin(lambda: len(self.case.received) >= 2)
        target = list(self.control._peers)[1]
        self.motion.enqueue_latest(self.case.sample(2, t=2))
        pending = self.control._peers[target]['motion_pending']
        key = ('b' * 32, 'c' * 32, 10055)
        earlier_peer = list(self.control._peers.values())[0]
        data, expected, accepted, _, guard = pending[key]
        observed_earlier_request = []

        def fail_discard():
            active = earlier_peer.get('motion_active')
            if active is not None and active['sent'] == 0 and active['key'] == key:
                observed_earlier_request.append(active['expected']['request_id'])
            else:
                observed_earlier_request.append(earlier_peer['motion_pending'][key][1]['request_id'])
            raise RuntimeError('reservation cleanup failed')

        pending[key] = (data, expected, accepted, fail_discard, guard)
        with self.assertRaisesRegex(RuntimeError, 'control channel faulted'):
            self.motion.enqueue_latest(self.case.sample(3, t=3))
        self.assertEqual(observed_earlier_request, [3])
        self.assertFalse(self.control._peers)
        self.assertTrue(self.control._failed)
        self.assertIsNone(self.control._reader_lease)
        with self.assertRaisesRegex(RuntimeError, 'control unavailable'):
            self.host.tick(0)
        self.assertFalse(any(sample['sequence'] == 3 for _, sample, _ in self.case.received))

    def test_active_discard_failure_fences_control(self):
        target = list(self.control._peers)[0]
        member = [item for item in self.case.delivery.membership() if item['id'] == 'peer_1']
        original_send = socket.socket.send

        def blocked_send(sock, data, *args, **kwargs):
            if sock is target:
                raise BlockingIOError()
            return original_send(sock, data, *args, **kwargs)

        self.motion.enqueue_latest(self.case.sample(), recipients=member)
        with patch.object(socket.socket, 'send', blocked_send):
            self.host.tick(.01)
        active = self.control._peers[target]['motion_active']
        self.assertEqual(active['sent'], 0)
        reader_lease = object()

        def fail_discard():
            self.control._reader_lease = reader_lease
            raise RuntimeError('reservation cleanup failed')

        active['discarded'] = fail_discard
        with self.assertRaisesRegex(RuntimeError, 'control channel faulted'):
            self.motion.enqueue_latest(self.case.sample(2, t=2), recipients=member)
        self.assertTrue(self.control._failed)
        self.assertFalse(self.control._peers)
        self.assertIs(self.control._reader_lease, reader_lease)

    def test_barrier_discard_failure_fences_control(self):
        self.motion.enqueue_latest(self.case.sample())
        self.spin(lambda: len(self.case.received) >= 2)
        self.motion.enqueue_latest(self.case.sample(2, t=2))
        target = list(self.control._peers)[1]
        pending = self.control._peers[target]['motion_pending']
        key = ('b' * 32, 'c' * 32, 10055)
        data, expected, accepted, _, guard = pending[key]

        def fail_discard():
            raise RuntimeError('reservation cleanup failed')

        pending[key] = (data, expected, accepted, fail_discard, guard)
        with self.assertRaisesRegex(RuntimeError, 'control channel faulted'):
            self.control.motion_barrier()
        self.assertTrue(self.control._failed)
        self.assertFalse(self.control._peers)
        self.assertIsNone(self.control._reader_lease)
        with self.assertRaisesRegex(RuntimeError, 'control unavailable'):
            self.host.tick(0)

    def test_unsent_active_frame_is_replaced_even_with_full_pending_queue(self):
        target = list(self.control._peers)[0]
        target_member = [member for member in self.case.delivery.membership()
                         if member['id'] == 'peer_1']
        self.control._latest_motion.limit = 1
        self.motion.track('b' * 32, 'c' * 32, 10056)
        guard_calls = []
        original_send = socket.socket.send

        def blocked_send(sock, data, *args, **kwargs):
            if sock is target:
                raise BlockingIOError()
            return original_send(sock, data, *args, **kwargs)

        self.motion.enqueue_latest(self.case.sample(), recipients=target_member,
                                   _guard=lambda: guard_calls.append('old'))
        with patch.object(socket.socket, 'send', blocked_send):
            self.host.tick(.01)
        active = self.control._peers[target]['motion_active']
        self.assertEqual(active['sent'], 0)
        deadline = active['deadline']
        self.assertEqual(guard_calls, ['old'])

        other_ship = self.case.sample()
        other_ship['index'] = 10056
        self.motion.enqueue_latest(other_ship, recipients=target_member)
        self.motion.enqueue_latest(self.case.sample(2, t=2), recipients=target_member,
                                   _guard=lambda: guard_calls.append('new'))
        self.assertIn(target, self.control._peers)
        self.assertEqual(active['deadline'], deadline)
        self.assertEqual(active['expected']['request_id'], 2)
        self.assertEqual(len(self.control._peers[target]['motion_pending']), 1)
        track = self.motion._tracks[('b' * 32, 'c' * 32, 10055)]
        identity = (target_member[0]['id'], target_member[0]['incarnation'])
        self.assertEqual(track['latest_frames'][identity], 'sector_a')

        self.spin(self.control._motion_idle)
        received = [(sample['index'], sample['sequence'])
                    for handle, sample, _ in self.case.received if handle == 1]
        self.assertEqual(received, [(10055, 2), (10056, 1)])
        self.assertEqual(guard_calls.count('old'), 1)
        self.assertIn('new', guard_calls)
        self.assertEqual(track['peer_samples'][identity][0], 2)

    def test_replacing_unsent_frame_discards_older_pending_copy(self):
        target = list(self.control._peers)[0]
        member = [item for item in self.case.delivery.membership() if item['id'] == 'peer_1']
        original_send = socket.socket.send

        def blocked_send(sock, data, *args, **kwargs):
            if sock is target:
                raise BlockingIOError()
            return original_send(sock, data, *args, **kwargs)

        self.motion.enqueue_latest(self.case.sample(), recipients=member)
        with patch.object(socket.socket, 'send', blocked_send):
            self.host.tick(.01)
        peer = self.control._peers[target]
        active = peer['motion_active']
        callbacks = []
        active_discard = active['discarded']

        def discard_active():
            callbacks.append('active')
            active_discard()

        active['discarded'] = discard_active
        # Model a pending copy left by an earlier queue implementation.
        peer['motion_pending'][active['key']] = (
            active['data'], active['expected'], active['accepted'],
            lambda: callbacks.append('pending'), active['guard'])
        self.motion.enqueue_latest(self.case.sample(2, t=2), recipients=member)
        self.assertEqual(callbacks, ['active', 'pending'])
        self.assertNotIn(active['key'], peer['motion_pending'])
        self.spin(self.control._motion_idle)
        self.assertEqual([sample['sequence'] for handle, sample, _ in self.case.received
                          if handle == 1], [2])

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
