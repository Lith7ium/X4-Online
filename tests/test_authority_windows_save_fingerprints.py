"""Simulated Windows stat differences; no Wine, Windows or X4 execution."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority import file_fingerprints
from authority.client_save_staging import copy_offered_save
from authority.experimental_client_load import ExperimentalClientLoad
from authority.load_messages import Offer


def changed_stat(info, **changes):
    fields = ('st_mode', 'st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    values = {name: getattr(info, name) for name in fields}
    values.update(changes)
    return SimpleNamespace(**values)


class WindowsSaveFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'download'
        self.data = b'synthetic checkpoint bytes'
        self.source.write_bytes(self.data)
        self.offer = Offer(world_epoch='epoch', connection_handle=1, baseline_id=1, load_generation=1,
            attempt_id='a' * 32, checkpoint_id='checkpoint-' + 'b' * 32,
            sha256=hashlib.sha256(self.data).hexdigest(), size=len(self.data), name='j1.xml.gz')
        self.marker = 'c' * 32
        self.real_fstat = os.fstat
        self.real_lstat = os.lstat
        self.fd_ctime_delta = 2_000_000
        self.path_ctime_delta = 0

    def fstat(self, fd):
        info = self.real_fstat(fd)
        return changed_stat(info, st_ctime_ns=info.st_ctime_ns + self.fd_ctime_delta)

    def lstat(self, path, *args, **kwargs):
        info = self.real_lstat(path, *args, **kwargs)
        return changed_stat(info, st_ctime_ns=info.st_ctime_ns + self.path_ctime_delta)

    def stat_patches(self, *, windows):
        stack = self.enterContext
        stack(patch.object(file_fingerprints, '_WINDOWS', windows))
        stack(patch.object(os, 'fstat', side_effect=self.fstat))
        stack(patch.object(os, 'lstat', side_effect=self.lstat))

    def test_windows_copy_and_claim_allow_stable_cross_api_ctime_difference(self):
        self.stat_patches(windows=True)
        target = self.root / 'save_009.xml.gz'
        copy_offered_save(self.source, target, self.offer, pump=lambda: None)
        self.assertEqual(target.read_bytes(), self.data)
        client = ExperimentalClientLoad(enabled=True, offer=self.offer, expected_marker=self.marker)
        client.verify_staged(target)
        client.observe_load_requested(self.offer.attempt_id)
        client.observe_loaded_marker(self.offer.attempt_id, self.marker)
        client.observe_pause(self.offer.attempt_id, True)
        self.assertEqual(client.make_claim(self.offer.attempt_id).marker, self.marker)

    def test_linux_rejects_cross_api_ctime_difference(self):
        self.stat_patches(windows=False)
        with self.assertRaisesRegex(ValueError, 'changed before copying'):
            copy_offered_save(self.source, self.root / 'save_009.xml.gz', self.offer, pump=lambda: None)
        client = ExperimentalClientLoad(enabled=True, offer=self.offer, expected_marker=self.marker)
        with self.assertRaisesRegex(ValueError, 'changed before reading'):
            client.verify_staged(self.source)

    def test_windows_path_and_descriptor_ctime_changes_during_copy_fail(self):
        for changed in ('path', 'descriptor'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                self.path_ctime_delta = 0
                self.fd_ctime_delta = 2_000_000
                calls = 0
                def pump():
                    nonlocal calls
                    calls += 1
                    if calls == 9:
                        if changed == 'path': self.path_ctime_delta += 1
                        else: self.fd_ctime_delta += 1
                with patch.object(file_fingerprints, '_WINDOWS', True), \
                     patch.object(os, 'fstat', side_effect=self.fstat), \
                     patch.object(os, 'lstat', side_effect=self.lstat):
                    with self.assertRaises(ValueError):
                        copy_offered_save(self.source, Path(directory) / 'save_009.xml.gz', self.offer, pump=pump)

    def test_windows_both_staged_fingerprints_are_rechecked_at_claim(self):
        self.stat_patches(windows=True)
        for changed in ('path', 'descriptor'):
            with self.subTest(changed=changed):
                self.path_ctime_delta = 0
                self.fd_ctime_delta = 2_000_000
                client = ExperimentalClientLoad(enabled=True, offer=self.offer, expected_marker=self.marker)
                client.verify_staged(self.source)
                client.observe_load_requested(self.offer.attempt_id)
                client.observe_loaded_marker(self.offer.attempt_id, self.marker)
                client.observe_pause(self.offer.attempt_id, True)
                if changed == 'path': self.path_ctime_delta += 1
                else: self.fd_ctime_delta += 1
                with self.assertRaisesRegex(ValueError, 'changed during load attempt'):
                    client.make_claim(self.offer.attempt_id)

    def test_windows_cross_api_identity_and_metadata_must_match(self):
        self.stat_patches(windows=True)
        info = self.real_lstat(self.source)
        for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns'):
            with self.subTest(field=field):
                altered = changed_stat(info, **{field: getattr(info, field) + 1})
                self.assertFalse(file_fingerprints.same_path_and_descriptor(info, altered))


if __name__ == '__main__':
    unittest.main()
