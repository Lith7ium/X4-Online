"""Client-side timing only: fake clocks and no X4 or helper process."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_witness_guard_client as subject
import authority_recovered_loopback_server as supervisor


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class GuardTimingTests(unittest.TestCase):
    def test_pump_and_send_are_measured_without_changing_order(self):
        clock = Clock()
        timing = subject.GuardClientTiming(clock)
        guard = subject.WitnessGuardClient.__new__(subject.WitnessGuardClient)
        guard.timing = timing
        guard.sock = object()
        events = []

        def pump():
            events.append('pump')
            clock.advance(3)

        def send(sock, payload, deadline, check):
            events.append('send-start')
            self.assertEqual(payload, b'{"op":"CHECK"}')
            check()
            clock.advance(2)
            events.append('send-end')

        guard.pump = pump
        guard._check = guard._pump
        with patch.object(subject, 'send_frame', send):
            guard._send({'op': 'CHECK'}, 100)
        self.assertEqual(events, ['send-start', 'pump', 'send-end'])
        self.assertEqual(timing.snapshot()['pump'], {'calls': 1, 'seconds': 3.0})
        # Send includes its nested pump; the values are not additive.
        self.assertEqual(timing.snapshot()['send'], {'calls': 1, 'seconds': 5.0})

    def test_response_select_wait_is_measured_even_on_failure(self):
        clock = Clock()
        timing = subject.GuardClientTiming(clock)
        guard = subject.WitnessGuardClient.__new__(subject.WitnessGuardClient)
        guard.timing = timing
        guard.sock = object()
        guard._check = lambda: None
        error = OSError('select failed')

        def failing_select(*_args):
            clock.advance(4)
            raise error

        with patch.object(subject.select, 'select', failing_select), \
             patch.object(subject.time, 'monotonic', return_value=0):
            with self.assertRaises(OSError) as caught:
                guard._read(10)
        self.assertIs(caught.exception, error)
        self.assertEqual(timing.snapshot()['response_wait'], {'calls': 1, 'seconds': 4.0})

    def test_pump_failure_is_preserved_and_counted(self):
        clock = Clock()
        timing = subject.GuardClientTiming(clock)
        guard = subject.WitnessGuardClient.__new__(subject.WitnessGuardClient)
        guard.timing = timing
        error = RuntimeError('pump failed')

        def fail():
            clock.advance(2)
            raise error

        guard.pump = fail
        with self.assertRaises(RuntimeError) as caught:
            guard._pump()
        self.assertIs(caught.exception, error)
        self.assertEqual(timing.snapshot()['pump'], {'calls': 1, 'seconds': 2.0})

    def test_failed_diagnostic_clock_does_not_change_pump_result(self):
        def broken_clock():
            raise OSError('clock unavailable')

        guard = subject.WitnessGuardClient.__new__(subject.WitnessGuardClient)
        guard.timing = subject.GuardClientTiming(broken_clock)
        guard.pump = lambda: True
        self.assertIs(guard._pump(), True)
        self.assertEqual(guard.timing.snapshot()['pump']['calls'], 0)

    def test_timing_requires_one_idle_owned_guard(self):
        guard = subject.WitnessGuardClient.__new__(subject.WitnessGuardClient)
        guard.owner = threading.get_ident()
        guard.state = 'ready'
        guard.timing = None
        timing = subject.GuardClientTiming(Clock())
        self.assertIs(guard.enable_timing(timing), timing)
        with self.assertRaises(ValueError):
            guard.enable_timing()
        self.assertFalse(supervisor.diagnostic_guard_timing(object(), False))
        args = type('Args', (), {'diagnostic_guard_timing': True})()
        with self.assertRaises(ValueError):
            supervisor.diagnostic_guard_timing(args, False)
        self.assertTrue(supervisor.diagnostic_guard_timing(args, True))


if __name__ == '__main__':
    unittest.main()
