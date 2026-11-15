"""Owned dummy processes only; never launch X4 or manipulate its lock."""
import os
from pathlib import Path
import select
import signal
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/dev'))
from authority_helper_lifecycle import OwnedHelper


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'pidfd_open') and
                     hasattr(signal, 'pidfd_send_signal'), 'Linux pidfd required')
class HelperLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.read, self.write = os.pipe2(os.O_CLOEXEC)
        self.addCleanup(os.close, self.read); self.addCleanup(os.close, self.write)
        self.helpers = []
        self.addCleanup(self.cleanup_helpers)

    def cleanup_helpers(self):
        for helper in reversed(self.helpers): helper.stop()

    def helper(self, body):
        return OwnedHelper([sys.executable, '-c', body, str(self.write)],
                           registry=self.helpers, pass_fds=(self.write,))

    def test_gate_blocks_execution_until_released(self):
        helper = self.helper('import os,sys;os.write(int(sys.argv[1]),b"ready")')
        self.assertEqual(select.select([self.read], [], [], .05)[0], [])
        helper.release()
        self.assertEqual(select.select([self.read], [], [], 2)[0], [self.read])
        self.assertEqual(os.read(self.read, 5), b'ready')
        self.assertEqual(helper.proc.wait(timeout=2), 0)
        self.assertEqual(helper.stop(), 0)

    def test_unreleased_helper_is_stopped_before_execution(self):
        helper = self.helper('import os,sys;os.write(int(sys.argv[1]),b"bad")')
        helper.stop()
        self.assertIsNotNone(helper.proc.poll())
        self.assertEqual(select.select([self.read], [], [], .05)[0], [])
        with self.assertRaises(RuntimeError): helper.release()

    def test_stuck_helper_is_killed_and_reaped(self):
        body = ('import os,sys,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);'
                'os.write(int(sys.argv[1]),b"ready");time.sleep(60);'
                'os.write(int(sys.argv[1]),b"late")')
        helper = self.helper(body); helper.release()
        self.assertEqual(select.select([self.read], [], [], 2)[0], [self.read])
        self.assertEqual(os.read(self.read, 5), b'ready')
        pid = helper.proc.pid
        self.assertEqual(helper.stop(grace=.05), -signal.SIGKILL)
        with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
        self.assertEqual(select.select([self.read], [], [], .05)[0], [])

    def test_failed_pidfd_open_reaps_registered_gated_child(self):
        with patch('authority_helper_lifecycle.os.pidfd_open', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError): self.helper('raise AssertionError("must not execute")')
        self.assertEqual(len(self.helpers), 1)
        self.assertIsNotNone(self.helpers[0].proc.poll())
        self.assertIsNone(self.helpers[0].gate)

    def test_ignored_sigchld_is_refused_before_spawn(self):
        previous = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        try:
            with self.assertRaises(ValueError): self.helper('pass')
            self.assertEqual(self.helpers, [])
        finally: signal.signal(signal.SIGCHLD, previous)

    def test_changed_sigchld_refuses_unconfirmed_cleanup(self):
        helper = self.helper('pass')
        previous = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        try:
            with self.assertRaisesRegex(RuntimeError, 'SIGCHLD changed'): helper.stop()
        finally: signal.signal(signal.SIGCHLD, previous)
        helper.stop()

    def test_externally_reaped_child_is_not_reported_as_success(self):
        helper = self.helper('pass'); helper.release()
        _, status = os.waitpid(helper.proc.pid, 0)
        try:
            with self.assertRaisesRegex(RuntimeError, 'reaped externally'): helper.stop()
            self.assertIsNotNone(helper.pidfd)
        finally:
            helper.proc.returncode = os.waitstatus_to_exitcode(status)
            os.close(helper.pidfd); helper.pidfd = None
            self.helpers.remove(helper)

    def test_interrupted_gate_write_marks_helper_as_possibly_released(self):
        helper = self.helper('import time;time.sleep(60)')
        original = os.write
        def write_then_interrupt(fd, data):
            original(fd, data)
            raise InterruptedError('after gate write')
        with patch('authority_helper_lifecycle.os.write', side_effect=write_then_interrupt):
            with self.assertRaises(InterruptedError): helper.release()
        self.assertTrue(helper.released)
        helper.stop()
        self.assertIsNotNone(helper.proc.poll())


if __name__ == '__main__': unittest.main()
