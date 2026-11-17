"""Offline file and short-write checks; no X4 or Windows execution."""
import hashlib
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority.client_save_staging import _write_all, copy_offered_save
import authority.client_save_staging as staging
from authority.load_messages import Offer


class ClientSaveStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = b'a small synthetic save'
        self.source = self.root / 'download'
        self.source.write_bytes(self.data)
        self.offer = Offer(world_epoch='epoch', connection_handle=1, baseline_id=1, load_generation=1,
                           attempt_id='a' * 32, checkpoint_id='checkpoint-' + 'b' * 32,
                           sha256=hashlib.sha256(self.data).hexdigest(), size=len(self.data), name='j1.xml.gz')

    def test_short_writes_are_completed(self):
        class PartialWriter:
            def __init__(self): self.data = bytearray()
            def write(self, data):
                count = min(3, len(data))
                self.data.extend(data[:count])
                return count
        target = PartialWriter()
        pumps = []
        _write_all(target, self.data, lambda: pumps.append(True))
        self.assertEqual(bytes(target.data), self.data)
        self.assertGreater(len(pumps), 2)

    def test_zero_write_fails(self):
        class StalledWriter:
            def write(self, data): return 0
        with self.assertRaises(OSError):
            _write_all(StalledWriter(), self.data, lambda: None)

    def test_invalid_slot_and_existing_symlink_are_untouched(self):
        with self.assertRaises(ValueError):
            copy_offered_save(self.source, self.root / 'other.xml.gz', self.offer, pump=lambda: None)
        previous = self.root / 'previous'
        previous.write_bytes(b'old data')
        target = self.root / 'save_009.xml.gz'
        try:
            target.symlink_to(previous)
        except (OSError, NotImplementedError):
            self.skipTest('symbolic links unavailable')
        with self.assertRaises(FileExistsError):
            copy_offered_save(self.source, target, self.offer, pump=lambda: None)
        self.assertEqual(previous.read_bytes(), b'old data')
        self.assertTrue(target.is_symlink())

    def test_oversized_source_stays_bounded_and_is_retained(self):
        self.source.write_bytes(self.data + b'extra')
        target = self.root / 'save_009.xml.gz'
        with self.assertRaises(ValueError):
            copy_offered_save(self.source, target, self.offer, pump=lambda: None)
        self.assertLessEqual(target.stat().st_size, len(self.data))
        self.assertEqual(self.source.read_bytes(), self.data + b'extra')

    def test_dangling_target_symlink_is_not_followed_or_replaced(self):
        missing = self.root / 'missing'
        target = self.root / 'save_009.xml.gz'
        try:
            target.symlink_to(missing)
        except (OSError, NotImplementedError):
            self.skipTest('symbolic links unavailable')
        with self.assertRaises(FileExistsError):
            copy_offered_save(self.source, target, self.offer, pump=lambda: None)
        self.assertTrue(target.is_symlink())
        self.assertFalse(missing.exists())
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_streams_more_than_one_chunk(self):
        data = b'x' * (1024 * 1024 + 31)
        self.source.write_bytes(data)
        offer = replace(self.offer, size=len(data), sha256=hashlib.sha256(data).hexdigest())
        target = self.root / 'save_009.xml.gz'
        copy_offered_save(self.source, target, offer, pump=lambda: None)
        self.assertEqual(target.read_bytes(), data)

    def test_changed_source_and_nonregular_source_are_rejected(self):
        target = self.root / 'save_009.xml.gz'
        real_write = staging._write_all
        def change_source(outgoing, block, pump):
            real_write(outgoing, block, pump)
            with self.source.open('ab') as source:
                source.write(b'changed')
        with patch.object(staging, '_write_all', side_effect=change_source):
            with self.assertRaises(ValueError):
                copy_offered_save(self.source, target, self.offer, pump=lambda: None)
        self.assertTrue(target.exists())
        other_target = self.root / 'save_010.xml.gz'
        with self.assertRaises(ValueError):
            copy_offered_save(self.root, other_target, self.offer, pump=lambda: None)
        self.assertFalse(other_target.exists())

    def test_io_failure_retains_the_created_target(self):
        for operation in ('_write_all', 'fsync'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'save_009.xml.gz'
                owner = staging if operation == '_write_all' else staging.os
                with patch.object(owner, operation, side_effect=OSError('synthetic I/O failure')):
                    with self.assertRaises(OSError):
                        copy_offered_save(self.source, target, self.offer, pump=lambda: None)
                self.assertTrue(target.exists())
                self.assertEqual(self.source.read_bytes(), self.data)


if __name__ == '__main__': unittest.main()
