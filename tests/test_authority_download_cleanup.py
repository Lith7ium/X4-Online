"""Fault injection for the isolated download runner's owned resources."""
import signal
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_download_load_live as subject


class DownloadCleanupTests(unittest.TestCase):
    def test_interrupted_lock_creation_remains_registered_for_cleanup(self):
        lockbox = []
        lock_stat = object()

        def create_lock(*_args):
            signal.raise_signal(signal.SIGTERM)
            return 55, lock_stat

        with patch.object(subject.live, 'create_lock_target', side_effect=create_lock), \
             patch.object(subject.live, 'release_lock_target') as release:
            with self.assertRaises(InterruptedError):
                subject.create_owned_lock(1, 2, lockbox)
            errors = []
            subject.finish_owned_lock(*lockbox[0], True, errors)
        release.assert_called_once_with(subject.snapshot.LOCK_TARGET, 55, lock_stat)
        self.assertEqual(errors, [])

    def test_service_failure_still_stops_process_and_retains_lock(self):
        service = Mock()
        service.close_and_drain.side_effect = TimeoutError('drain')
        process = Mock()
        result = {'success': False, 'error': 'original load failure'}
        errors = []
        with patch.object(subject.snapshot, 'stop_owned', return_value=[]) as stop, \
             patch.object(subject.live, 'release_lock_target') as release, \
             patch.object(subject.os, 'close') as close:
            stopped = subject.stop_owned_resources([service], [(process, 123)], result, errors)
            subject.finish_owned_lock(55, object(), stopped, errors)
        service.close_and_drain.assert_called_once_with(timeout=2)
        stop.assert_called_once_with(process, 123)
        release.assert_not_called()
        close.assert_called_once_with(55)
        self.assertEqual(result['error'], 'original load failure')
        self.assertEqual(result['owned_processes_remaining'], [])
        self.assertFalse(result['owned_cleanup_confirmed'])
        self.assertTrue(any('file service cleanup failed' in error for error in errors))
        self.assertTrue(any('lock retained' in error for error in errors))

    def test_process_failure_or_remaining_members_retains_lock(self):
        for outcome in ([321], RuntimeError('stop failed')):
            with self.subTest(outcome=outcome):
                errors = []
                result = {}
                process = Mock()
                service = Mock()
                with patch.object(subject.snapshot, 'stop_owned') as stop, \
                     patch.object(subject.live, 'release_lock_target') as release, \
                     patch.object(subject.os, 'close') as close:
                    if isinstance(outcome, Exception):
                        stop.side_effect = outcome
                    else:
                        stop.return_value = outcome
                    stopped = subject.stop_owned_resources([service], [(process, 123)], result, errors)
                    subject.finish_owned_lock(55, object(), stopped, errors)
                service.close_and_drain.assert_called_once_with(timeout=2)
                release.assert_not_called()
                close.assert_called_once_with(55)
                self.assertFalse(result['owned_cleanup_confirmed'])
                self.assertEqual(result['owned_processes_remaining'], None if isinstance(outcome, Exception) else outcome)

    def test_all_confirmed_resources_allow_lock_release(self):
        errors = []
        service = Mock()
        process = Mock()
        lock_stat = object()
        with patch.object(subject.snapshot, 'stop_owned', return_value=[]), \
             patch.object(subject.live, 'release_lock_target') as release:
            stopped = subject.stop_owned_resources([service], [(process, 123)], {}, errors)
            subject.finish_owned_lock(55, lock_stat, stopped, errors)
        release.assert_called_once_with(subject.snapshot.LOCK_TARGET, 55, lock_stat)
        self.assertEqual(errors, [])

    def test_missing_start_identity_and_failed_drain_both_reported(self):
        service = Mock()
        service.close_and_drain.side_effect = TimeoutError()
        process = Mock()
        process.poll.return_value = None
        errors = []
        result = {}
        stopped = subject.stop_owned_resources([service], [(process, None)], result, errors)
        self.assertFalse(stopped)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=15)
        self.assertIsNone(result['owned_processes_remaining'])
        self.assertEqual(len(errors), 2)


if __name__ == '__main__':
    unittest.main()
