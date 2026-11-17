"""The fixture watcher accepts appends without accepting changed evidence."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import authority_saved_fixture_log as subject


class SavedFixtureLogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'engine.log'
        self.path.write_bytes(b'first line\n')

    def test_append_during_capture_waits_for_next_poll(self):
        original_read = os.read
        changed = False

        def append_once(fd, size):
            nonlocal changed
            data = original_read(fd, size)
            if not changed:
                changed = True
                with self.path.open('ab') as stream:
                    stream.write(b'second line\n')
            return data

        with patch.object(subject.os, 'read', side_effect=append_once):
            raw, snapshot, caught_up = subject.capture(self.path, None, 1000)
        self.assertEqual(raw, b'first line\n')
        self.assertFalse(caught_up)
        raw, _, caught_up = subject.capture(self.path, snapshot, 1000)
        self.assertEqual(raw, b'first line\nsecond line\n')
        self.assertTrue(caught_up)

    def test_replacement_truncation_and_rewrite_during_capture_fail(self):
        for mode in ('replace', 'truncate', 'rewrite'):
            with self.subTest(mode=mode):
                self.path.write_bytes(b'first line\n')
                original_read = os.read
                changed = False

                def change_once(fd, size):
                    nonlocal changed
                    data = original_read(fd, size)
                    if not changed:
                        changed = True
                        if mode == 'replace':
                            other = self.path.with_suffix('.new')
                            other.write_bytes(b'first line\n')
                            other.replace(self.path)
                        elif mode == 'truncate':
                            self.path.write_bytes(b'short')
                        else:
                            with self.path.open('r+b') as stream:
                                stream.write(b'X')
                    return data

                with patch.object(subject.os, 'read', side_effect=change_once):
                    with self.assertRaisesRegex(ValueError, 'engine log:'):
                        subject.capture(self.path, None, 1000)

    def test_previous_prefix_cannot_be_rewritten_even_when_file_grows(self):
        _, snapshot, _ = subject.capture(self.path, None, 1000)
        self.path.write_bytes(b'Xirst line\nnew line\n')
        with self.assertRaisesRegex(ValueError, 'previously observed prefix changed'):
            subject.capture(self.path, snapshot, 1000)

    def test_disappearance_and_path_replacement_are_rejected(self):
        _, snapshot, _ = subject.capture(self.path, None, 1000)
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, 'disappeared'):
            subject.capture(self.path, snapshot, 1000)
        self.path.write_bytes(b'first line\n')
        with self.assertRaisesRegex(ValueError, 'replaced or truncated'):
            subject.capture(self.path, snapshot, 1000)


if __name__ == '__main__':
    unittest.main()
