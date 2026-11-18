"""Focused control lifecycle for the shared one-shot participant motion owner."""
import unittest

from authority.participant_motion import ParticipantMotion


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
