"""Focused offline tests for the private opt-in fixture save guard."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority_fixture_save_guards import FixtureSaveGuards
import authority_two_x4_live as supervisor


class FixtureSaveGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.entries = []
        for index in range(3):
            path = Path(self.temp.name) / str(index)
            data = bytes([index]) * (index + 3)
            path.write_bytes(data)
            path.chmod(0o400)
            self.entries.append((path, hashlib.sha256(data).hexdigest()))
        self.full_calls = []
        def full_sha(path):
            self.full_calls.append(path)
            return hashlib.sha256(path.read_bytes()).hexdigest()
        self.guards = FixtureSaveGuards(full_sha)
        self.addCleanup(self.guards.close)

    def test_default_full_then_pinned_boundaries_and_full_again(self):
        path, expected = self.entries[0]
        self.assertTrue(self.guards.check(path, expected))
        self.assertEqual(self.full_calls, [path])
        self.guards.open(self.entries)
        for item in self.entries:
            self.assertTrue(self.guards.check(*item))
        self.assertEqual(self.full_calls, [path])
        self.assertTrue(self.guards.boundary(lambda: True))
        self.assertEqual(self.guards.metrics['metadata_checks'], 3)
        self.assertEqual(self.guards.metrics['digest_checks'], 3)
        self.assertEqual(self.guards.metrics['verified_digest_bytes'], 12)
        self.assertGreaterEqual(self.guards.metrics['digest_seconds'], 0)
        self.guards.close()
        self.assertTrue(self.guards.check(path, expected))
        self.assertEqual(self.full_calls, [path, path])

    def test_wrong_path_hash_mode_or_duplicate_refused(self):
        self.guards.open(self.entries)
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.guards.check(Path(self.temp.name) / 'foreign', self.entries[0][1])
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.guards.check(self.entries[0][0], 'f' * 64)
        self.guards.close()
        with self.assertRaisesRegex(ValueError, 'invalid fixture save path'):
            self.guards.open([self.entries[0]] * 3)
        self.entries[1][0].chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'read-only'):
            self.guards.open(self.entries)

    def test_changed_save_and_guard_failure_do_not_pass(self):
        self.guards.open(self.entries)
        path, expected = self.entries[0]
        path.chmod(0o600)
        with self.assertRaises(ValueError):
            self.guards.check(path, expected)
        with self.assertRaises(RuntimeError):
            self.guards.check(path, expected)
        self.guards.close()
        path.chmod(0o400)
        self.guards.open(self.entries)
        with self.assertRaisesRegex(RuntimeError, 'live guard failed'):
            self.guards.boundary(lambda: False)
        with self.assertRaisesRegex(RuntimeError, 'invalidated'):
            self.guards.boundary(lambda: True)
        self.assertEqual(self.guards.metrics['verified_digest_bytes'], 0)

    def test_client_context_substitutes_only_save_hash_and_fences_identities(self):
        target, digest = self.entries[0]
        config = self.entries[1][0]
        parameters = dict(deadline=20, server_proc='server', server_started=1, server_identity=('s', 1),
                          client_proc='client', client_started=2, client_identity=('c', 2), game='game',
                          home='home', uid=1000, steam='steam', target=target, ticket={'sha256':digest},
                          expected={config:'config'})
        identities = lambda proc, *_: ('s', 1) if proc == 'server' else ('c', 2)
        self.guards.open(self.entries)
        with patch.object(supervisor.time, 'monotonic', return_value=10), \
             patch.object(supervisor.client, 'game_identity', side_effect=identities), \
             patch.object(supervisor.live, 'steam_identity', return_value='steam'), \
             patch.object(supervisor.live, 'sha', return_value='config') as hashes:
            self.assertTrue(supervisor.check_live_context(**parameters, verify_target=self.guards.check))
            self.assertEqual(hashes.call_args_list[0].args, (config,))
            self.assertEqual(hashes.call_count, 1)
        with patch.object(supervisor.time, 'monotonic', return_value=10), \
             patch.object(supervisor.client, 'game_identity', side_effect=[('s', 1), ('c', 2), ('s', 1), ('changed', 3)]), \
             patch.object(supervisor.live, 'steam_identity', return_value='steam'), \
             patch.object(supervisor.live, 'sha', return_value='config'):
            with self.assertRaises(RuntimeError):
                supervisor.check_live_context(**parameters, verify_target=self.guards.check)

    def test_mode_change_after_pin_is_rejected_and_descriptor_closed(self):
        import authority_fixture_save_guards as module
        real_lstat = module.os.lstat
        real_pin = module.PinnedFileGuard
        calls = []
        pins = []
        def record_pin(*args):
            pin = real_pin(*args)
            pins.append(pin)
            return pin
        def changing_lstat(path):
            calls.append(path)
            if len(calls) == 5:
                Path(path).chmod(0o600)
            return real_lstat(path)
        with patch.object(module.os, 'lstat', side_effect=changing_lstat), \
             patch.object(module, 'PinnedFileGuard', side_effect=record_pin):
            with self.assertRaisesRegex(ValueError, 'changed while pinning'):
                self.guards.open(self.entries)
        self.assertEqual(len(pins), 1)
        self.assertIsNone(pins[0]._fd)
        self.entries[0][0].chmod(0o400)
        self.guards.open(self.entries)
        self.assertTrue(self.guards.boundary(lambda: True))

    def test_failed_cleanup_fences_repeated_close_and_all_guard_operations(self):
        import authority_fixture_save_guards as module
        guards = FixtureSaveGuards(lambda path: hashlib.sha256(path.read_bytes()).hexdigest())
        real_close = module.PinnedFileGuard.close
        pins = []

        def fail_one_close(pin):
            if pin is pins[0]:
                raise OSError('injected close failure')
            return real_close(pin)

        with patch.object(module.PinnedFileGuard, 'close', fail_one_close):
            guards.open(self.entries)
            pins = [entry[0] for entry in guards._guards.values()]
            try:
                with self.assertRaisesRegex(OSError, 'injected close failure'):
                    guards.close()
                for operation in (guards.close, lambda: guards.check(*self.entries[0]),
                                  lambda: guards.boundary(lambda: True),
                                  lambda: guards.open(self.entries)):
                    with self.assertRaisesRegex(RuntimeError, 'owner is fenced'):
                        operation()
                self.assertIsNotNone(guards._guards)
            finally:
                # The deliberately failed descriptor still belongs to this test.
                for pin in pins:
                    if pin._fd is not None:
                        real_close(pin)

    def test_failed_open_rollback_fences_owner(self):
        import authority_fixture_save_guards as module
        guards = FixtureSaveGuards(lambda path: hashlib.sha256(path.read_bytes()).hexdigest())
        real_pin = module.PinnedFileGuard
        pins = []

        def fail_check():
            raise ValueError('injected pin failure')

        def fail_close():
            raise OSError('injected rollback failure')

        def failing_pin(*args):
            pin = real_pin(*args)
            pins.append(pin)
            pin.check = fail_check
            pin.close = fail_close
            return pin

        try:
            with patch.object(module, 'PinnedFileGuard', side_effect=failing_pin):
                with self.assertRaises(BaseExceptionGroup) as error:
                    guards.open(self.entries)
            self.assertEqual([str(item) for item in error.exception.exceptions],
                             ['injected pin failure', 'injected rollback failure'])
            for operation in (guards.close, lambda: guards.check(*self.entries[0]),
                              lambda: guards.boundary(lambda: True),
                              lambda: guards.open(self.entries)):
                with self.assertRaisesRegex(RuntimeError, 'owner is fenced'):
                    operation()
        finally:
            for pin in pins:
                if pin._fd is not None:
                    real_pin.close(pin)


if __name__ == '__main__':
    unittest.main()
