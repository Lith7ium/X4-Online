"""Ownership and failure paths for the isolated checkpoint-load runner."""
from contextlib import ExitStack
import os
import signal
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_load_live as subject


class LoadCleanupTests(unittest.TestCase):
    def test_signal_during_lock_creation_leaves_a_registered_lock(self):
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

    def test_failure_after_lock_before_spawn_releases_it_and_retains_error(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as patches:
            root = Path(directory)
            game = root / 'game'
            (game / 'extensions').mkdir(parents=True)
            auth = root / 'authority'
            auth.touch()
            target = root / 'staged-save'
            checkpoint = SimpleNamespace(sha256='expected')
            user = SimpleNamespace(pw_dir=directory, pw_uid=1000, pw_gid=1000, pw_name='user')
            args = SimpleNamespace(out=root / 'result', store=root, game=game,
                                   display=':0', timeout=10, seed=1, checkpoint_id='checkpoint')
            lock_stat = object()
            patches.enter_context(patch.object(subject.os, 'geteuid', return_value=1000))
            patches.enter_context(patch.dict(os.environ, {'XAUTHORITY': str(auth)}))
            patches.enter_context(patch('pwd.getpwuid', return_value=user))
            patches.enter_context(patch.object(subject.snapshot, 'output_path', return_value=args.out))
            patches.enter_context(patch.object(subject, 'local_directory', return_value=root))
            patches.enter_context(patch.object(subject, 'CheckpointStore'))
            patches.enter_context(patch.object(subject.shutil, 'which', return_value='/usr/bin/bwrap'))
            patches.enter_context(patch.object(subject.live, 'x4_executables', return_value=[]))
            patches.enter_context(patch.object(subject.live, 'steam_identity', return_value='steam'))
            patches.enter_context(patch.object(subject.live, 'sha', side_effect=[subject.live.EXE_SHA, 'different']))
            patches.enter_context(patch.object(subject.snapshot, 'prepare_case', return_value=(root, root, [], root)))
            patches.enter_context(patch.object(subject, 'stage_checkpoint', return_value=(checkpoint, target)))
            patches.enter_context(patch.object(subject, 'verify_origin'))
            patches.enter_context(patch.object(subject, 'install_probe'))
            patches.enter_context(patch.object(subject.live, 'create_lock_target', return_value=(55, lock_stat)))
            release = patches.enter_context(patch.object(subject.live, 'release_lock_target'))
            spawn = patches.enter_context(patch.object(subject, 'spawn_owned_gated'))
            result = subject.run(args)
        spawn.assert_not_called()
        release.assert_called_once_with(subject.snapshot.LOCK_TARGET, 55, lock_stat)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'staged checkpoint changed before launch')
        self.assertTrue(result['owned_cleanup_confirmed'])

    def test_surviving_or_unknown_process_keeps_lock_and_original_error(self):
        for outcome in ([321], RuntimeError('cannot determine process group')):
            with self.subTest(outcome=outcome):
                process = Mock()
                result = {'success': False, 'error': 'original load failure'}
                errors = []
                with patch.object(subject.snapshot, 'stop_owned') as stop, \
                     patch.object(subject.live, 'release_lock_target') as release, \
                     patch.object(subject.os, 'close') as close:
                    if isinstance(outcome, Exception):
                        stop.side_effect = outcome
                    else:
                        stop.return_value = outcome
                    stopped = subject.stop_owned_processes([(process, 123)], result, errors)
                    subject.finish_owned_lock(55, object(), stopped, errors)
                release.assert_not_called()
                close.assert_called_once_with(55)
                self.assertEqual(result['error'], 'original load failure')
                self.assertFalse(result['owned_cleanup_confirmed'])
                self.assertTrue(any('lock retained' in error for error in errors))
                self.assertEqual(result['owned_processes_remaining'], None if isinstance(outcome, Exception) else outcome)

    def test_known_stopped_process_allows_lock_release(self):
        result = {}
        errors = []
        lock_stat = object()
        with patch.object(subject.snapshot, 'stop_owned', return_value=[]), \
             patch.object(subject.live, 'release_lock_target') as release:
            stopped = subject.stop_owned_processes([(Mock(), 123)], result, errors)
            subject.finish_owned_lock(55, lock_stat, stopped, errors)
        release.assert_called_once_with(subject.snapshot.LOCK_TARGET, 55, lock_stat)
        self.assertTrue(result['owned_cleanup_confirmed'])
        self.assertEqual(errors, [])

    def test_failed_identity_never_releases_exec_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / 'launched'
            command = [sys.executable, '-c', 'from pathlib import Path; Path(sys.argv[1]).touch()', str(sentinel)]
            # The command cannot run: the start identity fails before the gate is opened.
            command[2] = 'import sys; ' + command[2]
            processes = []
            with patch.object(subject.live, 'start_ticks', side_effect=RuntimeError('identity unavailable')):
                with self.assertRaises(RuntimeError):
                    subject.spawn_owned_gated(command, root / 'process.log', processes)
            self.assertEqual(len(processes), 1)
            result = {}
            errors = []
            self.assertFalse(subject.stop_owned_processes(processes, result, errors))
            self.assertIsNone(result['owned_processes_remaining'])
            self.assertFalse(sentinel.exists())

    def test_gated_process_can_be_stopped_and_group_confirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            processes = []
            process, started = subject.spawn_owned_gated(
                [sys.executable, '-c', 'import time; time.sleep(60)'],
                Path(directory) / 'process.log', processes)
            try:
                result = {}
                errors = []
                self.assertTrue(subject.stop_owned_processes(processes, result, errors))
                self.assertEqual(result['owned_processes_remaining'], [])
                self.assertEqual(errors, [])
            finally:
                if process.poll() is None:
                    subject.snapshot.stop_owned(process, started)


if __name__ == '__main__':
    unittest.main()
