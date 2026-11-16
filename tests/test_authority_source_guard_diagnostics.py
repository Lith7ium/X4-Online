"""Fixed failure labels preserve the source guard's evaluation order."""
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC


class SourceGuardDiagnostics(unittest.TestCase):
    def test_saved_guard_failure_reasons_without_extra_checks(self):
        failure_reasons = (
            'guard_false', 'operation_deadline', 'phase_changed', 'motion_failed',
            'delivery_failed', 'host_failed', 'thread_changed', 'local_socket_changed',
            'peer_socket_changed',
        )
        for reason in failure_reasons:
            with self.subTest(reason=reason):
                trace = []
                clock = [1.0]
                host = SimpleNamespace(_failed=False)
                delivery = SimpleNamespace(_failed=False, _host=host)
                motion = SimpleNamespace(_failed=False, _delivery=delivery)

                class Socket:
                    def getsockname(self):
                        trace.append('local')
                        return 'changed' if reason == 'local_socket_changed' and 'saved' in trace else 'local'

                    def getpeername(self):
                        trace.append('peer_socket')
                        return 'changed' if reason == 'peer_socket_changed' and 'saved' in trace else 'peer'

                bridge = ExperimentalSourceMotionIPC.__new__(ExperimentalSourceMotionIPC)
                bridge._motion = motion
                bridge._state = 'pulling'
                bridge._owner = threading.get_ident()
                bridge._sock = Socket()
                bridge._local, bridge._peer = 'local', 'peer'
                bridge._guard = lambda: trace.append('guard') or True
                bridge._validate = lambda _peer: trace.append('validate') or True
                bridge._call_fenced = lambda callback, *args: callback(*args)
                bridge._saved_guard = object()

                def saved_guard():
                    trace.append('saved')
                    if reason == 'operation_deadline':
                        clock[0] = 10.0
                    if reason == 'phase_changed':
                        bridge._state = 'changed'
                    if reason == 'motion_failed':
                        motion._failed = True
                    if reason == 'delivery_failed':
                        delivery._failed = True
                    if reason == 'host_failed':
                        host._failed = True
                    if reason == 'thread_changed':
                        bridge._owner = -1
                    return reason != 'guard_false'

                bridge._saved_fence = saved_guard
                with patch('authority.experimental_source_motion_ipc.time.monotonic', side_effect=lambda: clock[0]):
                    with self.assertRaisesRegex(RuntimeError, 'saved baseline guard failed: ' + reason):
                        bridge._check(10.0, 'pulling')
                self.assertEqual(trace[:4], ['guard', 'local', 'peer_socket', 'validate'])
                self.assertEqual(trace.count('saved'), 1)
                self.assertEqual(trace.count('guard'), 1)
                self.assertEqual(trace.count('validate'), 1)
                if reason not in ('local_socket_changed', 'peer_socket_changed'):
                    self.assertEqual(trace, ['guard', 'local', 'peer_socket', 'validate', 'saved'])


if __name__ == '__main__':
    unittest.main()
