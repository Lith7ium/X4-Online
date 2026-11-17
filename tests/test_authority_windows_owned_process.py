"""Synthetic lifecycle tests; no Windows identity or X4 behavior is proven."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import authority.experimental_windows_owned_process as subject


class FakeChild:
    def __init__(self):
        self._handle = object()
        self.pid = 123
        self.returncode = None
        self.termination_calls = 0
        self.fail_terminate = False

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        if self.returncode is None:
            raise subprocess.TimeoutExpired('synthetic', timeout)
        return self.returncode

    def terminate(self):
        self.termination_calls += 1
        if self.fail_terminate:
            raise OSError('unknown stop effect')


class OwnedWindowsProcessTest(unittest.TestCase):
    def setUp(self):
        runtime = patch.object(subject, '_windows_runtime', return_value=True)
        runtime.start()
        self.addCleanup(runtime.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cwd = self.temporary.name
        self.command = [str(Path(sys.executable).resolve()), '-c', 'pass']
        self.owner = subject.ExperimentalWindowsOwnedProcess(enabled=True)

    def start_fake(self, fake):
        with patch.object(subject.subprocess, 'Popen', return_value=fake):
            self.owner.start(self.command, cwd=self.cwd, env={})

    def test_timeout_and_exit_are_distinct(self):
        child = FakeChild()
        self.start_fake(child)
        self.assertIsNone(self.owner.poll())
        self.assertIsNone(self.owner.wait(0))
        self.assertFalse(self.owner.cleanup_confirmed)
        child.returncode = 7
        self.assertEqual(self.owner.wait(.01), 7)
        self.assertTrue(self.owner.cleanup_confirmed)
        self.assertEqual(self.owner.poll(), 7)
        with self.assertRaises(RuntimeError):
            self.owner.start(self.command, cwd=self.cwd, env={})

    def test_unclear_start_is_never_cleanup_or_retry(self):
        possibly_started = []
        def interrupted(*args, **kwargs):
            possibly_started.append(FakeChild())
            raise InterruptedError('start outcome uncertain')
        with patch.object(subject.subprocess, 'Popen', side_effect=interrupted):
            with self.assertRaises(InterruptedError):
                self.owner.start(self.command, cwd=self.cwd, env={})
            with self.assertRaises(RuntimeError):
                self.owner.start(self.command, cwd=self.cwd, env={})
        self.assertEqual(len(possibly_started), 1)
        self.assertFalse(self.owner.cleanup_confirmed)
        with self.assertRaises(RuntimeError):
            self.owner.wait(0)
        self.assertFalse(self.owner.cleanup_confirmed)

    def test_x4_basename_is_rejected_before_start(self):
        with patch.object(subject.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'X4 startup'):
                self.owner.start([str(Path(self.cwd) / 'X4.exe')], cwd=self.cwd, env={})
            popen.assert_not_called()
        self.assertFalse(self.owner.cleanup_confirmed)

    def test_stop_dispatched_once_even_after_failure(self):
        child = FakeChild()
        child.fail_terminate = True
        self.start_fake(child)
        with self.assertRaises(OSError):
            self.owner.terminate()
        with self.assertRaises(RuntimeError):
            self.owner.terminate()
        self.assertEqual(child.termination_calls, 1)
        self.assertFalse(self.owner.cleanup_confirmed)
        child.returncode = 1
        self.assertEqual(self.owner.wait(0), 1)
        self.assertTrue(self.owner.cleanup_confirmed)

    def test_changed_handle_cannot_be_used_or_declared_clean(self):
        child = FakeChild()
        self.start_fake(child)
        child._handle = object()
        with self.assertRaises(RuntimeError):
            self.owner.terminate()
        self.assertEqual(child.termination_calls, 0)
        self.assertFalse(self.owner.cleanup_confirmed)

    def test_direct_synthetic_child_is_waited_after_termination(self):
        # On non-Windows this wraps a real POSIX child to exercise orchestration;
        # it is not evidence of the Windows Popen handle implementation.
        actual_popen = subprocess.Popen
        children = []
        class WrappedChild:
            def __init__(self, *args, **kwargs):
                self.actual = actual_popen(*args, **kwargs)
                children.append(self.actual)
                self._handle = object()
                self.pid = self.actual.pid
            def poll(self): return self.actual.poll()
            def wait(self, timeout): return self.actual.wait(timeout=timeout)
            def terminate(self): self.actual.terminate()
        try:
            with patch.object(subject.subprocess, 'Popen', WrappedChild):
                self.owner.start([self.command[0], '-c', 'import time; time.sleep(60)'],
                                 cwd=self.cwd, env=dict(os.environ))
            self.assertIsNone(self.owner.poll())
            self.owner.terminate()
            self.assertIsNotNone(self.owner.wait(5))
            self.assertTrue(self.owner.cleanup_confirmed)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
