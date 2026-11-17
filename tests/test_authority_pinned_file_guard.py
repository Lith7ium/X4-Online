"""Offline checks of the opt-in diagnostic file pin; no X4 is started."""
import fcntl
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
from authority_pinned_file_guard import PinnedFileGuard


class PinnedFileGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'save.gz'
        self.contents = b'a' * (1024 * 1024 + 11)
        self.path.write_bytes(self.contents)
        self.digest = hashlib.sha256(self.contents).hexdigest()

    def pin(self):
        guard = PinnedFileGuard(self.path, self.digest)
        self.addCleanup(guard.close)
        return guard

    def test_check_is_metadata_only_and_digest_is_explicit(self):
        guard = self.pin()
        self.assertEqual(fcntl.fcntl(guard._fd, fcntl.F_GETFL) & os.O_ACCMODE, os.O_RDONLY)
        with patch('authority_pinned_file_guard.os.pread', side_effect=AssertionError('unexpected read')):
            self.assertTrue(guard.check())
        calls = []
        self.assertTrue(guard.verify_digest(guard=lambda: calls.append(True) or True))
        self.assertEqual(len(calls), 3)

    def test_context_closes_and_empty_file_hashes(self):
        self.path.write_bytes(b'')
        with PinnedFileGuard(self.path, hashlib.sha256(b'').hexdigest()) as guard:
            self.assertTrue(guard.verify_digest())
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            guard.check()
        guard.close()

    def test_wrong_digest_is_not_accepted(self):
        with PinnedFileGuard(self.path, '0' * 64) as guard:
            self.assertTrue(guard.check())
            with self.assertRaisesRegex(ValueError, 'digest differs'):
                guard.verify_digest()
            with self.assertRaisesRegex(RuntimeError, 'invalidated'):
                guard.verify_digest()
            with self.assertRaisesRegex(RuntimeError, 'invalidated'):
                guard.check()

    def test_replacement_symlink_and_deletion_are_rejected(self):
        for action in ('replace', 'symlink', 'delete'):
            with self.subTest(action=action):
                self.path.write_bytes(self.contents)
                with self.pin() as guard:
                    moved = self.path.with_suffix('.old')
                    self.path.rename(moved)
                    if action == 'replace':
                        self.path.write_bytes(self.contents)
                    elif action == 'symlink':
                        self.path.symlink_to(moved)
                    with self.assertRaises(ValueError):
                        guard.check()
                    if self.path.exists() or self.path.is_symlink():
                        self.path.unlink()
                    moved.unlink()

    def test_modified_truncated_and_chmod_are_rejected(self):
        for action in ('modify', 'truncate', 'chmod'):
            with self.subTest(action=action):
                self.path.write_bytes(self.contents)
                self.path.chmod(0o600)
                with self.pin() as guard:
                    if action == 'modify':
                        with self.path.open('r+b') as stream:
                            stream.write(b'b')
                    elif action == 'truncate':
                        self.path.write_bytes(b'')
                    else:
                        self.path.chmod(0o400)
                    with self.assertRaises(ValueError):
                        guard.check()

    def test_mutation_during_digest_and_guard_failure_abort(self):
        guard = self.pin()
        calls = []
        def mutate_during_digest():
            calls.append(True)
            if len(calls) == 2:
                with self.path.open('r+b') as stream:
                    stream.write(b'b')
            return True
        with self.assertRaises(ValueError):
            guard.verify_digest(guard=mutate_during_digest)
        guard.close()
        self.path.write_bytes(self.contents)
        with self.pin() as second:
            with self.assertRaisesRegex(RuntimeError, 'live guard failed'):
                second.verify_digest(guard=lambda: False)
            with self.assertRaisesRegex(RuntimeError, 'invalidated'):
                second.verify_digest()
            with self.assertRaisesRegex(ValueError, 'callable'):
                second.verify_digest(guard=True)

    def test_metadata_check_failure_invalidates_guard_permanently(self):
        guard = self.pin()
        original_mode = self.path.stat().st_mode & 0o777
        self.path.chmod(original_mode ^ 0o100)
        with self.assertRaisesRegex(ValueError, 'identity or metadata changed'):
            guard.check()
        self.path.chmod(original_mode)
        with self.assertRaisesRegex(RuntimeError, 'invalidated'):
            guard.check()
        with self.assertRaisesRegex(RuntimeError, 'invalidated'):
            guard.verify_digest()
        guard.close()

    def test_digest_metadata_failure_invalidates_guard_permanently(self):
        guard = self.pin()
        self.path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'identity or metadata changed'):
            guard.verify_digest()
        with self.assertRaisesRegex(RuntimeError, 'invalidated'):
            guard.check()
        guard.close()

    def test_requires_absolute_path_regular_file_and_valid_digest(self):
        with self.assertRaises(ValueError):
            PinnedFileGuard('relative', self.digest)
        with self.assertRaises(ValueError):
            PinnedFileGuard(self.path, 'bad')
        link = self.path.with_suffix('.link')
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            PinnedFileGuard(link, self.digest)
        with self.assertRaises(ValueError):
            PinnedFileGuard(self.path.parent, self.digest)

    def test_callback_cannot_replace_expected_digest_or_other_context(self):
        guard = PinnedFileGuard(self.path, '0' * 64)
        try:
            def replace_expected():
                guard._expected_sha256 = self.digest
                return True
            with self.assertRaisesRegex(RuntimeError, 'context changed'):
                guard.verify_digest(guard=replace_expected)
            with self.assertRaisesRegex(RuntimeError, 'refusing cleanup'):
                guard.close()
        finally:
            # Test owns the descriptor and repairs the deliberately damaged state.
            guard._expected_sha256 = '0' * 64
            guard.close()

    def test_swallowed_reentry_cannot_make_digest_succeed(self):
        for operation in ('check', 'close', 'verify_digest'):
            with self.subTest(operation=operation):
                guard = self.pin()
                def reenter():
                    try:
                        getattr(guard, operation)()
                    except RuntimeError:
                        pass
                    return True
                with self.assertRaisesRegex(RuntimeError, 'context changed'):
                    guard.verify_digest(guard=reenter)
                with self.assertRaisesRegex(RuntimeError, 'invalidated'):
                    guard.check()
                guard.close()

    def test_replaced_descriptor_is_not_closed_as_owned(self):
        guard = self.pin()
        foreign_path = self.path.with_suffix('.foreign')
        foreign_path.write_bytes(b'foreign')
        foreign_fd = os.open(foreign_path, os.O_RDONLY)
        try:
            replaced_fd = guard._fd
            os.dup2(foreign_fd, replaced_fd)
            with self.assertRaisesRegex(ValueError, 'identity or metadata changed'):
                guard.check()
            with self.assertRaisesRegex(RuntimeError, 'replaced; refusing cleanup'):
                guard.close()
            self.assertEqual(os.pread(replaced_fd, 7, 0), b'foreign')
        finally:
            os.close(foreign_fd)
            os.close(guard._fd)
            guard._fd = None

    def test_callback_replacing_descriptor_cannot_pass_digest(self):
        guard = self.pin()
        foreign_path = self.path.with_suffix('.foreign')
        foreign_path.write_bytes(b'foreign')
        foreign_fd = os.open(foreign_path, os.O_RDONLY)
        try:
            def replace_fd():
                os.dup2(foreign_fd, guard._fd)
                return True
            with self.assertRaisesRegex(ValueError, 'identity or metadata changed'):
                guard.verify_digest(guard=replace_fd)
            with self.assertRaisesRegex(RuntimeError, 'replaced; refusing cleanup'):
                guard.close()
        finally:
            os.close(foreign_fd)
            os.close(guard._fd)
            guard._fd = None


if __name__ == '__main__':
    unittest.main()
