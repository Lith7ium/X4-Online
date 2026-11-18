"""Position-clock protocol checks; synthetic transport, no X4/native writes."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from authority.experimental_tcp_motion import check_motion_progress, motion_digest, motion_value
from authority.experimental_tcp_participants import ExperimentalTCPParticipants
import test_authority_experimental_tcp_motion as fixture


def sample(sequence=1, *, game_time=100, capture_time=200):
    value = fixture.MotionTCP.sample(sequence, t=game_time)
    del value['velocity']
    return dict(value, version=3, capture_time=capture_time,
                real_velocity={'x': 4, 'y': 0, 'z': 0})


class PositionClockSchema(unittest.TestCase):
    def test_exact_schema_detachment_and_digest_include_both_clocks_and_rate(self):
        original = sample()
        detached = motion_value(original)
        digest = motion_digest(original)
        encoded = json.dumps(original, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')
        self.assertEqual(digest, hashlib.sha256(encoded).hexdigest())
        original['real_velocity']['x'] = 99
        self.assertEqual(detached['real_velocity']['x'], 4)
        for mutation in ({'capture_time': 201}, {'source_time': 101}, {'real_velocity': None}):
            self.assertNotEqual(digest, motion_digest(detached | mutation))
        self.assertIsNone(motion_value(sample() | {'real_velocity': None})['real_velocity'])

    def test_rejects_mixed_missing_boolean_and_nonfinite_fields(self):
        invalid = [sample() | {'velocity': None}, sample() | {'orientation': {}},
                   sample() | {'angular_rate': None}, sample() | {'version': True},
                   sample() | {'capture_time': 10**1000},
                   sample() | {'real_velocity': {'x': 0, 'y': 0}},
                   sample() | {'real_velocity': {'x': 5001, 'y': 0, 'z': 0}}]
        for field in sample():
            missing = sample()
            del missing[field]
            invalid.append(missing)
        for field in ('capture_time', 'source_time', 'x', 'y', 'z'):
            for number in (True, float('nan'), float('inf'), -float('inf')):
                invalid.append(sample() | {field: number})
        for number in (True, float('nan'), float('inf')):
            invalid.append(sample() | {'real_velocity': {'x': number, 'y': 0, 'z': 0}})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                motion_value(value)
        with self.assertRaises(ValueError):
            motion_value(sample(), despawn=True)

    def test_clock_progression_and_version_fence_preserve_legacy_rules(self):
        first = sample()
        check_motion_progress(first, None)
        check_motion_progress(sample(2, capture_time=201), first)  # Game clock may stall.
        for later in (sample(2, capture_time=200), sample(2, capture_time=199),
                      sample(2, game_time=99, capture_time=201)):
            with self.subTest(later=later), self.assertRaises(ValueError):
                check_motion_progress(later, first)
        legacy = fixture.MotionTCP.sample()
        pose = dict(legacy, version=2, orientation={'yaw': 0, 'pitch': 0, 'roll': 0}, angular_rate=None)
        versions = [legacy, pose, first]
        for previous in versions:
            for later in versions:
                if previous['version'] != later['version']:
                    with self.subTest(versions=(previous['version'], later['version'])), self.assertRaises(ValueError):
                        check_motion_progress(later, previous)
        for previous in (legacy, pose):
            with self.assertRaises(ValueError):
                check_motion_progress(previous | {'sequence': 2}, previous)
            check_motion_progress(previous | {'sequence': 2, 'source_time': 2}, previous)
        with self.assertRaisesRegex(ValueError, 'frame transition'):
            check_motion_progress(sample(2, capture_time=201) | {'sector_macro': 'other'}, first)
        check_motion_progress(sample(2, capture_time=201) | {'sector_macro': 'other', 'real_velocity': None}, first)


class PositionClockTransport(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.MotionTCP('test_invalid_values_and_no_fake_velocity')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setup_pair()
        self.motion = self.fixture.motion
        self.control = self.fixture.case.control

    def test_serialized_stall_preserves_wire_digest_then_rejects_version_switch(self):
        exchanges = []
        def exchange(owner, connection, peer, others, payload, expected, deadline, **options):
            request = json.loads(payload)
            self.assertEqual(expected['sample_sha256'], motion_digest(request['sample']))
            exchanges.append(request)
            return expected
        with patch.object(ExperimentalTCPParticipants, '_exchange', side_effect=exchange):
            self.assertTrue(self.motion.send(sample()))
            time.sleep(.005)
            self.assertTrue(self.motion.send(sample(2, capture_time=201)))
            self.assertEqual([row['sample']['capture_time'] for row in exchanges], [200, 200, 201, 201])
            with self.assertRaisesRegex(ValueError, 'version changed'):
                self.motion.send(fixture.MotionTCP.sample(3, t=101))
        self.assertTrue(self.motion._failed)

    def test_latest_enqueued_state_rejects_clock_and_version_changes_before_receipt(self):
        self.control.enable_latest_motion(enabled=True)
        self.assertTrue(self.motion.enqueue_latest(sample()))
        self.assertTrue(self.motion.enqueue_latest(sample(2, capture_time=201)))
        track = self.motion._tracks[('b'*32, 'c'*32, 10055)]
        before = copy.deepcopy(track)
        for invalid in (sample(3, capture_time=201), sample(3, capture_time=199),
                        sample(3, capture_time=202, game_time=99), fixture.MotionTCP.sample(3, t=101)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.motion.enqueue_latest(invalid)
            self.assertEqual(track, before)
        for peer in self.control._peers.values():
            payload, expected, *_ = next(iter(peer['motion_pending'].values()))
            self.assertEqual(json.loads(payload)['sample'], sample(2, capture_time=201))
            self.assertEqual(expected['sample_sha256'], motion_digest(sample(2, capture_time=201)))
        self.assertTrue(self.control.motion_barrier())

    def test_native_preflight_and_apply_do_not_accept_v3(self):
        for method in ('preflight', 'apply_once'):
            self.motion._allow_apply = True
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, 'not implemented'):
                getattr(self.motion, method)(sample())
            # These operations fail closed; reset solely to exercise the second refusal.
            self.motion._failed = self.fixture.delivery._failed = self.fixture.case.host._failed = False


if __name__ == '__main__':
    unittest.main()
