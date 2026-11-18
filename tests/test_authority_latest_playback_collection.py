"""Latest collector state/counter checks with deterministic fake owners; no X4."""
import copy
from contextlib import contextmanager
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.experimental_tcp_motion import motion_digest
import authority_latest_playback_collection as subject


class FakeClock:
    def __init__(self):
        self.value = 10.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        assert seconds >= 0
        self.value += seconds


class FakeOwners:
    def __init__(self, clock, *, unsent_ticks=0, first_ack_delay=.15):
        self.clock = clock
        self.recipient = {'id': 'peer_1', 'incarnation': 'a' * 32}
        self.key = ('b' * 32, 'c' * 32, 1318)
        self.track = {'sequence': 0, 'peer_samples': {}}
        self.peer = {'stage': 'admitted', 'motion_active': None}
        self.connection = object()
        self.pending = None
        self.queued = []
        self.begins = []
        self.sent = []
        self.acked = []
        self.replaced = []
        self.ticks = self.barriers = self.failures = 0
        self.unsent_ticks = unsent_ticks
        self.first_ack_delay = first_ack_delay
        self.defer_flags = []
        self.tick_hook = lambda: None
        self.next_sequence = lambda sequence: sequence
        self.latest = SimpleNamespace(blocked=False, world_blocked=False)
        self.session = SimpleNamespace(state='running', pending=None,
            players=((1, 'client'),), ready_players=((1, 'client'),))
        self.host = SimpleNamespace(_failed=False, _busy=False,
            _world=SimpleNamespace(session=self.session), tick=self.tick)
        self.control = SimpleNamespace(_failed=False, _reader_lease=None,
            _latest_motion=self.latest, _peers={self.connection: self.peer},
            _motion_idle=self.idle, motion_barrier=self.barrier)
        self.host._control = self.control
        self.delivery = SimpleNamespace(_host=self.host, _failed=False, _active=False,
            _incarnations={1: self.recipient['incarnation']},
            membership=lambda: (copy.deepcopy(self.recipient),),
            _peers=lambda: ((1,), {1: (self.connection, self.peer)}))
        self.motion = SimpleNamespace(_delivery=self.delivery, _failed=False,
            _tracks={self.key: self.track})
        self.source = SimpleNamespace(_motion=self.motion, _latest=True, _owner=threading.get_ident(),
            _indices={1318}, _epoch=self.key[0], _generation=self.key[1], state='ready',
            begin_latest=self.begin, poll_latest=self.poll, _fail=self.fail)
        self.control._latest_source = self.source

    def idle(self):
        return self.pending is None and self.peer['motion_active'] is None

    def begin(self):
        self.begins.append({'time': self.clock.value, 'acks': list(self.acked)})
        self.source.state = 'pulling'
        return True

    def poll(self):
        sequence = self.next_sequence(len(self.queued) + 1)
        sample = dict(version=1, epoch=self.key[0], generation=self.key[1], index=1318,
            sequence=sequence, sector_macro='sector_a', source_time=self.clock.value,
            x=self.clock.value, y=2, z=3, velocity=None)
        self.source.state = 'ready'
        self.queued.append(copy.deepcopy(sample))
        self.track['sequence'] = sequence
        active = self.peer['motion_active']
        if active is not None and active['sent'] == 0:
            self.replaced.append(active['sample']['sequence'])
            self.peer['motion_active'] = self.frame(sample)
        else:
            if self.pending is not None:
                self.replaced.append(self.pending['sequence'])
            self.pending = sample
        return True, sample

    def frame(self, sample):
        return {'key': self.key, 'sent': 0, 'sample': sample, 'ack_at': None,
                'expected': {'request_id': sample['sequence'], 'sample_sha256': motion_digest(sample)}}

    def tick(self, timeout, *, defer_world):
        assert timeout == 0
        self.defer_flags.append(defer_world)
        self.ticks += 1
        self.clock.value += .005
        if self.peer['motion_active'] is None and self.pending is not None:
            self.peer['motion_active'] = self.frame(self.pending)
            self.pending = None
        active = self.peer['motion_active']
        if active is not None:
            sequence = active['sample']['sequence']
            if active['sent'] == 0 and self.ticks > self.unsent_ticks:
                active['sent'] = 1
                delay = self.first_ack_delay if sequence == 1 else .01
                active['ack_at'] = self.clock.value + delay
                self.sent.append((sequence, self.clock.value))
            if active['sent'] and self.clock.value >= active['ack_at']:
                self.track['peer_samples'][(self.recipient['id'], self.recipient['incarnation'])] = (
                    sequence, motion_digest(active['sample']))
                self.acked.append(sequence)
                self.peer['motion_active'] = None
        self.tick_hook()

    def barrier(self):
        assert self.idle(), 'barrier must not discard pending samples'
        assert self.acked[-1] == self.queued[-1]['sequence']
        self.barriers += 1
        self.latest.blocked = True
        return True

    def fail(self):
        self.failures += 1
        self.source.state = 'failed'
        self.host._failed = self.delivery._failed = self.motion._failed = True


class LatestPlaybackCollectionTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.addCleanup(patch.stopall)
        patch.object(subject.time, 'monotonic', self.clock.monotonic).start()
        patch.object(subject.time, 'sleep', self.clock.sleep).start()

    def collect(self, owners, **options):
        arguments = dict(source=owners.source, motion=owners.motion, host=owners.host,
            recipient=owners.recipient, deadline=self.clock.value + 3, check=lambda: True,
            sample_count=6, interval=.02)
        arguments.update(options)
        return subject.collect_latest_playback(**arguments)

    def test_collects_while_first_ack_pending_and_returns_real_ack_subset(self):
        owners = FakeOwners(self.clock)
        progress = {}
        result = self.collect(owners, progress=progress)
        self.assertEqual([row['sequence'] for row in result['queued_samples']], list(range(1, 7)))
        self.assertEqual([row['sequence'] for row in result['acknowledged_samples']], [1, 6])
        self.assertEqual(owners.begins[1]['acks'], [])
        self.assertTrue(owners.replaced)
        self.assertEqual(owners.barriers, 1)
        self.assertEqual(owners.source.state, 'ready')
        self.assertTrue(all(owners.defer_flags))
        self.assertEqual(progress['state'], 'complete')
        self.assertEqual(progress['acknowledged_sequences'], [1, 6])
        self.assertEqual(progress['queued_samples'], result['queued_samples'])
        self.assertEqual(progress['acknowledged_samples'], result['acknowledged_samples'])
        self.assertGreater(result['stats']['operations']['pump']['calls'], 6)
        result['queued_samples'][0]['x'] = -1
        self.assertNotEqual(owners.queued[0]['x'], -1)
        progress['stats']['sample_times'].clear()
        self.assertEqual(len(result['stats']['sample_times']), 6)

    def test_unsent_first_frame_is_never_replaced(self):
        owners = FakeOwners(self.clock, unsent_ticks=10)
        result = self.collect(owners)
        self.assertNotIn(1, owners.replaced)
        self.assertGreaterEqual(owners.begins[1]['time'], owners.sent[0][1])
        self.assertEqual(result['stats']['first_frame_started_at'], owners.sent[0][1])

    def test_ack_before_next_collection_also_protects_enrollment(self):
        owners = FakeOwners(self.clock, first_ack_delay=0)
        result = self.collect(owners)
        self.assertEqual(result['acknowledged_samples'][0]['sequence'], 1)
        self.assertIn(1, owners.begins[1]['acks'])
        self.assertEqual(owners.barriers, 1)

    def test_unknown_or_mismatched_ack_never_becomes_receipt(self):
        for receipt in ((99, '0' * 64), (1, '0' * 64), (2, '0' * 64)):
            with self.subTest(receipt=receipt):
                owners = FakeOwners(self.clock)
                owners.tick_hook = lambda: owners.track['peer_samples'].update({
                    ('peer_1', 'a' * 32): receipt})
                progress = {}
                with self.assertRaisesRegex(RuntimeError, 'ACK'):
                    self.collect(owners, progress=progress)
                self.assertEqual(progress['acknowledged_sequences'], [])
                self.assertEqual(owners.failures, 1)
                self.assertEqual(owners.barriers, 0)

    def test_ack_regression_is_rejected_after_a_confirmed_receipt(self):
        owners = FakeOwners(self.clock, first_ack_delay=0)
        def regress():
            if len(owners.acked) >= 2:
                first = owners.queued[0]
                owners.track['peer_samples'][('peer_1', 'a' * 32)] = (1, motion_digest(first))
        # Inject only after the collector observed the second ACK on a prior tick.
        original_tick = owners.tick
        def tick(*args, **kwargs):
            if len(owners.acked) >= 2:
                regress()
            else:
                original_tick(*args, **kwargs)
        owners.host.tick = tick
        progress = {}
        with self.assertRaisesRegex(RuntimeError, 'ACK'):
            self.collect(owners, progress=progress)
        self.assertGreaterEqual(len(progress['acknowledged_sequences']), 2)
        self.assertEqual(owners.failures, 1)

    def test_source_sequence_gap_faults_instead_of_becoming_latest_receipt(self):
        owners = FakeOwners(self.clock)
        owners.next_sequence = lambda number: number if number == 1 else number + 1
        progress = {}
        with self.assertRaisesRegex(RuntimeError, 'source identity or sequence'):
            self.collect(owners, progress=progress)
        self.assertEqual(progress['queued_sequences'], [1])
        self.assertEqual(len(progress['queued_samples']), 1)
        self.assertEqual(owners.failures, 1)

    def test_deadline_guard_and_membership_lifecycle_changes_fail_closed(self):
        for mode in ('deadline', 'guard', 'member', 'pending', 'peer', 'thread'):
            with self.subTest(mode=mode):
                owners = FakeOwners(self.clock, first_ack_delay=100)
                options = {'progress': {}}
                if mode == 'deadline':
                    options['deadline'] = self.clock.value + .03
                elif mode == 'guard':
                    options['check'] = lambda: False
                else:
                    def change():
                        if mode == 'member':
                            owners.recipient['incarnation'] = 'd' * 32
                        elif mode == 'pending':
                            owners.session.pending = object()
                        elif mode == 'peer':
                            owners.control._peers[owners.connection] = dict(owners.peer)
                        elif mode == 'thread':
                            owners.source._owner = -1
                    owners.tick_hook = change
                with self.assertRaises(RuntimeError):
                    self.collect(owners, **options)
                self.assertEqual(options['progress']['state'], 'failed')
                self.assertEqual(owners.failures, 1)
                self.assertEqual(owners.barriers, 0)

    def test_empty_completed_pull_does_not_advance_enrollment_sequence(self):
        owners = FakeOwners(self.clock)
        original_poll = owners.source.poll_latest
        attempts = 0
        def poll():
            nonlocal attempts
            attempts += 1
            if attempts in (1, 3):
                owners.source.state = 'ready'
                return True, None
            return original_poll()
        owners.source.poll_latest = poll
        result = self.collect(owners)
        self.assertEqual(result['stats']['empty_pulls'], 2)
        self.assertEqual([row['sequence'] for row in result['queued_samples']], list(range(1, 7)))
        self.assertEqual(result['acknowledged_samples'][0]['sequence'], 1)
        self.assertEqual(result['acknowledged_samples'][-1]['sequence'], 6)

    def test_queued_sample_is_retained_before_post_poll_guard_failure(self):
        owners = FakeOwners(self.clock)
        progress = {}
        def guard():
            return len(owners.queued) < 2
        with self.assertRaisesRegex(RuntimeError, 'external guard'):
            self.collect(owners, check=guard, progress=progress)
        self.assertEqual(progress['queued_sequences'], [1, 2])
        self.assertEqual(progress['queued_samples'][1], owners.queued[1])
        self.assertEqual(owners.failures, 1)

    def test_operation_scopes_are_balanced_and_finite_polling_preserves_deadline(self):
        owners = FakeOwners(self.clock)
        enters, exits = [], []
        @contextmanager
        def scope():
            enters.append(self.clock.value)
            try:
                yield
            finally:
                exits.append(self.clock.value)
        original_poll = owners.source.poll_latest
        owners.source.poll_latest = lambda: (False, None)
        with self.assertRaises(RuntimeError):
            self.collect(owners, scope=scope, deadline=self.clock.value + .03)
        self.assertEqual(len(enters), len(exits))
        self.assertGreater(len(enters), 1)
        self.assertEqual(owners.failures, 1)
        owners.source.poll_latest = original_poll


if __name__ == '__main__':
    unittest.main()
