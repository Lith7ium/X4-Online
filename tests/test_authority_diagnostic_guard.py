"""Deterministic policy checks with simulated time; no X4 or native writes."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest

from authority_diagnostic_guard import DiagnosticEnvironmentGuard, LinuxDiagnosticProcess


class DiagnosticGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.duration = 0.0
        self.environment_valid = True
        self.process_alive = True
        self.full_calls = 0
        self.immediate_calls = 0

    def full_check(self):
        self.full_calls += 1
        self.now += self.duration
        return self.environment_valid

    def immediate_check(self):
        self.immediate_calls += 1
        return self.process_alive

    def guard(self, **options):
        return DiagnosticEnvironmentGuard(full_check=self.full_check,
            immediate_check=self.immediate_check, clock=lambda: self.now, **options)

    def test_default_remains_fresh_and_cache_requires_bounded_explicit_age(self):
        guard = self.guard()
        self.assertTrue(guard())
        self.assertTrue(guard())
        self.assertEqual(self.full_calls, 2)
        for age in (-1, 0.251, True, float('nan'), float('inf'), '0.25'):
            with self.subTest(age=age), self.assertRaises(ValueError):
                self.guard(cache_seconds=age)

    def test_reuse_exposes_approved_stale_window_then_refreshes_at_exact_expiry(self):
        guard = self.guard(cache_seconds=0.25)
        guard()
        self.environment_valid = False
        self.now = 10.125
        self.assertTrue(guard())  # Explicitly accepted limitation of this mode.
        self.assertEqual(self.full_calls, 1)
        self.now = 10.25
        with self.assertRaisesRegex(RuntimeError, 'full diagnostic'):
            guard()
        self.environment_valid = True
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            guard()

    def test_refresh_time_consumes_lease_from_start_not_completion(self):
        self.duration = 0.125
        guard = self.guard(cache_seconds=0.25)
        guard()
        self.now = 10.249
        guard()
        self.assertEqual(self.full_calls, 1)
        self.now = 10.25
        guard()
        self.assertEqual(self.full_calls, 2)

    def test_slow_refresh_cannot_publish_an_already_expired_success(self):
        self.duration = 0.25
        guard = self.guard(cache_seconds=0.25)
        with self.assertRaises(TimeoutError):
            guard()
        with self.assertRaises(RuntimeError):
            guard()

    def test_process_exit_is_immediate_even_with_a_fresh_cached_result(self):
        guard = self.guard(cache_seconds=0.25)
        guard()
        self.process_alive = False
        with self.assertRaisesRegex(RuntimeError, 'immediate'):
            guard()
        self.assertEqual(self.full_calls, 1)

    def test_exit_during_full_check_and_slow_immediate_check_are_not_hidden(self):
        def exit_during_check():
            self.process_alive = False
            return True
        guard = DiagnosticEnvironmentGuard(full_check=exit_during_check,
            immediate_check=self.immediate_check, clock=lambda: self.now, cache_seconds=0.25)
        with self.assertRaisesRegex(RuntimeError, 'immediate'):
            guard()
        self.process_alive = True
        guard = self.guard(cache_seconds=0.25)
        guard()
        self.environment_valid = False
        def slow_immediate():
            self.now += 0.25
            return True
        guard._immediate_check = slow_immediate
        with self.assertRaisesRegex(RuntimeError, 'full diagnostic'):
            guard()

    def test_lifecycle_disables_reuse_and_forces_a_fresh_next_motion_check(self):
        guard = self.guard(cache_seconds=0.25)
        guard()
        with guard.strict():
            guard()
            guard()
        self.assertEqual(self.full_calls, 5)  # Initial, enter, two calls, exit.
        guard()
        self.assertEqual(self.full_calls, 6)
        guard.invalidate()
        guard()
        self.assertEqual(self.full_calls, 7)

    def test_lifecycle_boundary_detects_changes_and_fences_body_failures(self):
        guard = self.guard(cache_seconds=0.25)
        with self.assertRaisesRegex(RuntimeError, 'full diagnostic'):
            with guard.strict():
                self.environment_valid = False
        with self.assertRaises(RuntimeError):
            guard()
        self.environment_valid = True
        guard = self.guard(cache_seconds=0.25)
        with self.assertRaisesRegex(ValueError, 'control failed'):
            with guard.strict():
                raise ValueError('control failed')
        with self.assertRaises(RuntimeError):
            guard()

    def test_clock_regression_and_swallowed_reentry_fail_closed(self):
        guard = self.guard(cache_seconds=0.25)
        guard()
        self.now -= 1
        with self.assertRaisesRegex(RuntimeError, 'clock'):
            guard()
        def reenter():
            try:
                guard()
            except RuntimeError:
                pass
            return True
        guard = DiagnosticEnvironmentGuard(full_check=reenter,
            immediate_check=lambda: True, clock=lambda: self.now, cache_seconds=0.25)
        with self.assertRaises(RuntimeError):
            guard()


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'pidfd_open'),
                     'Linux pidfd diagnostic required')
class RetainedProcessTests(unittest.TestCase):
    def setUp(self):
        self.child = subprocess.Popen([sys.executable, '-c',
            'import sys; sys.stdin.buffer.read(1)'], stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_child)
        directory = Path('/proc') / str(self.child.pid)
        fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
        image = (directory / 'exe').stat()
        self.process = dict(pid=self.child.pid, start_ticks=int(fields[19]),
                            exe_dev=image.st_dev, exe_ino=image.st_ino)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.addCleanup(self.sock.close)

    def stop_child(self):
        if self.child.stdin is not None:
            self.child.stdin.close()
        if self.child.poll() is None:
            self.child.terminate()
        self.child.wait(timeout=5)

    def retained(self):
        retained = LinuxDiagnosticProcess(process=self.process, sockets=(self.sock,))
        self.addCleanup(retained.close)
        return retained

    def test_real_process_exit_refuses_a_fresh_cached_environment(self):
        retained = self.retained()
        full_calls = []
        def full_check():
            full_calls.append(True)
            return True
        guard = DiagnosticEnvironmentGuard(full_check=full_check,
            immediate_check=retained.check, cache_seconds=0.25, clock=lambda: 10)
        guard()
        self.stop_child()
        with self.assertRaisesRegex(RuntimeError, 'process exited'):
            guard()
        self.assertEqual(len(full_calls), 1)

    def test_replaced_local_descriptor_is_detected_without_remote_scan(self):
        retained = self.retained()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as replacement:
            replacement.bind(('127.0.0.1', 0))
            os.dup2(replacement.fileno(), self.sock.fileno())
            with self.assertRaisesRegex(RuntimeError, 'local socket'):
                retained.check()

    def test_wrong_process_lifetime_and_closed_handle_are_refused(self):
        wrong = dict(self.process, start_ticks=self.process['start_ticks'] + 1)
        with self.assertRaisesRegex(RuntimeError, 'process identity'):
            LinuxDiagnosticProcess(process=wrong, sockets=(self.sock,))
        retained = self.retained()
        retained.close()
        with self.assertRaisesRegex(RuntimeError, 'handle'):
            retained.check()


if __name__ == '__main__':
    unittest.main()
