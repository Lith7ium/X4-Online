"""Focused control lifecycle for the shared one-shot participant motion owner."""
import unittest

from authority.participant_motion import ParticipantMotion, RECOVERY_SETTER_EPOCH


class FakeSocket:
    address = ('127.0.0.1', 42000)

    def getsockname(self):
        return self.address

    def close(self):
        pass


class FakeMotionIPC:
    def __init__(self, sock, **options):
        self.options = options
        self.state = 'new'
        self.events = []

    def wait_ready(self):
        self.events.append('ready')
        self.state = 'ready'

    def __call__(self, sample, despawn):
        self.events.append(('sample', sample, despawn))
        return True

    def stop_remote(self):
        self.events.append('stop')
        return True

    def close(self):
        self.state = 'closed'


class ParticipantMotionControlTests(unittest.TestCase):
    def playback_owner(self, *, setter=False):
        config = {'motion': {
            'lease': 'a'*32, 'attempt': 'b'*32, 'epoch': RECOVERY_SETTER_EPOCH,
            'generation': 'd'*32, 'timeout': 1,
            'saved_playback_fixture': 'recovery_enh_870',
        }}
        if setter:
            config['motion']['saved_apply_fixture'] = 'recovery_enh_870'
        motion = ParticipantMotion(FakeSocket(), config, lambda: True, lambda address: True, FakeMotionIPC)
        motion.after_control('resume')
        return motion

    @staticmethod
    def real_sample(sequence=1, *, game_time=7, capture_time=100):
        return dict(version=3, epoch=RECOVERY_SETTER_EPOCH, generation='d'*32,
                    index=1318, sequence=sequence, sector_macro='cluster_06_sector001_macro',
                    source_time=game_time, capture_time=capture_time,
                    x=1000, y=2, z=3, real_velocity=None)

    def test_v3_playback_keeps_original_snapshot_and_accepts_game_stall(self):
        motion = self.playback_owner()
        first = self.real_sample()
        self.assertTrue(motion(first, False))
        self.assertEqual(motion.bridge.events[1], ('sample', first, False))
        first['capture_time'] = -1
        self.assertEqual(motion._playback_previous['capture_time'], 100)
        second = self.real_sample(3, capture_time=100.2)
        second['real_velocity'] = {'x': 4, 'y': 0, 'z': 0}
        self.assertTrue(motion(second, False))
        self.assertEqual(motion.confirmed_samples, 2)
        self.assertTrue(motion.stop())
        with self.assertRaisesRegex(RuntimeError, 'while paused'):
            motion(self.real_sample(4, capture_time=101), False)

    def test_v3_capture_game_version_and_fixture_regressions_never_dispatch(self):
        motion = self.playback_owner()
        with self.assertRaisesRegex(ValueError, 'sequence one'):
            motion(self.real_sample(2), False)
        self.assertIsNone(motion.bridge)
        motion(self.real_sample(), False)
        legacy = self.real_sample(2, capture_time=101)
        legacy['version'] = 1
        legacy['velocity'] = None
        del legacy['capture_time'], legacy['real_velocity']
        for value in (self.real_sample(2), self.real_sample(2, capture_time=99),
                      self.real_sample(2, game_time=6, capture_time=101),
                      self.real_sample(1, capture_time=101), legacy,
                      self.real_sample(2, capture_time=101) | {'index': 1319},
                      self.real_sample(2, capture_time=101) | {'sector_macro': 'other'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                motion(value, False)
        self.assertEqual(motion.confirmed_samples, 1)
        self.assertEqual(len(motion.bridge.events), 2)

    def test_v3_setter_refusal_precedes_bridge_creation(self):
        for operation in ('preflight', 'apply_once'):
            motion = self.playback_owner(setter=True)
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                getattr(motion, operation)(self.real_sample())
            self.assertIsNone(motion.bridge)

    def test_ready_is_lazy_and_stop_precedes_pause_without_rearming(self):
        config = {'motion': {
            'lease': 'a' * 32, 'attempt': 'b' * 32, 'epoch': 'c' * 32,
            'generation': 'd' * 32, 'timeout': 1,
        }}
        bridges = []

        def make_bridge(sock, **options):
            bridge = FakeMotionIPC(sock, **options)
            bridges.append(bridge)
            return bridge

        sock = FakeSocket()
        motion = ParticipantMotion(sock, config, lambda: True,
                                   lambda address: True, make_bridge)
        self.assertTrue(motion.before_control('resume'))
        self.assertFalse(motion.running)
        self.assertEqual(bridges, [])
        with self.assertRaisesRegex(RuntimeError, 'while paused'):
            motion({}, False)

        self.assertTrue(motion.after_control('resume'))
        self.assertTrue(motion.running)
        self.assertEqual(bridges, [])
        self.assertTrue(motion({'sequence': 1}, False))
        self.assertEqual(motion.confirmed_samples, 1)
        self.assertEqual(bridges[0].events, ['ready', ('sample', {'sequence': 1}, False)])
        self.assertTrue(bridges[0].options['guard']())
        sock.address = ('127.0.0.1', 42001)
        self.assertFalse(bridges[0].options['guard']())
        sock.address = motion.destination

        self.assertTrue(motion.before_control('pause'))
        self.assertEqual(bridges[0].events[-1], 'stop')
        self.assertFalse(motion.running)
        self.assertTrue(motion.stopped)
        self.assertTrue(motion.after_control('pause'))
        with self.assertRaisesRegex(RuntimeError, 'cannot resume'):
            motion.before_control('resume')


if __name__ == '__main__':
    unittest.main()
