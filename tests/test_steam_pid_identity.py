"""Steam identity uses fresh target-only /proc observations; no game launch."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import linux_gate_live as subject


class SteamIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'home'
        (self.home / '.steam').mkdir(parents=True)
        self.pid_file = self.home / '.steam/steam.pid'
        self.pid_file.write_text('123\n')
        self.proc = self.root / 'proc'
        self.target = self.proc / '123'
        self.target.mkdir(parents=True)
        self.write_status(100)
        (self.target / 'comm').write_text('steam\n')
        original_read = subject._steam_process_row
        self.reader = patch.object(subject, '_steam_process_row',
            side_effect=lambda path: original_read(self.proc / path.name))
        self.reader.start()
        self.addCleanup(self.reader.stop)
        self.process_scan = patch.object(subject, 'processes', side_effect=AssertionError('unexpected process scan'))
        self.process_scan.start()
        self.addCleanup(self.process_scan.stop)

    def write_status(self, start):
        fields = ['S', '42'] + ['0'] * 17 + [str(start)]
        (self.target / 'stat').write_text('123 (steam) ' + ' '.join(fields) + '\n')

    def test_reads_only_target_fresh_and_detects_recycled_pid(self):
        unrelated = self.proc / '124'
        unrelated.mkdir()
        (unrelated / 'stat').write_text('malformed')
        first = subject.steam_identity(self.home, os.getuid())
        self.write_status(101)
        second = subject.steam_identity(self.home, os.getuid())
        self.assertEqual(first, {'pid': 123, 'start': 100, 'uid': os.getuid()})
        self.assertEqual(second, {'pid': 123, 'start': 101, 'uid': os.getuid()})
        self.assertNotEqual(first, second)

    def test_missing_or_invalid_target_and_mismatched_identity_refuse(self):
        for field in ('missing_stat', 'missing_comm', 'invalid_stat', 'wrong_name', 'wrong_uid'):
            with self.subTest(field=field):
                self.write_status(100)
                (self.target / 'comm').write_text('steam\n')
                expected_uid = os.getuid()
                if field == 'missing_stat': (self.target / 'stat').unlink()
                if field == 'missing_comm': (self.target / 'comm').unlink()
                if field == 'invalid_stat': (self.target / 'stat').write_text('malformed')
                if field == 'wrong_name': (self.target / 'comm').write_text('other\n')
                if field == 'wrong_uid': expected_uid += 1
                exception = IndexError if field == 'invalid_stat' else RuntimeError
                with self.assertRaises(exception):
                    subject.steam_identity(self.home, expected_uid)

    def test_changed_pid_file_reads_new_target(self):
        first = subject.steam_identity(self.home, os.getuid())
        new_target = self.proc / '456'
        new_target.mkdir()
        fields = ['S', '42'] + ['0'] * 17 + ['200']
        (new_target / 'stat').write_text('456 (steam) ' + ' '.join(fields) + '\n')
        (new_target / 'comm').write_text('steam\n')
        self.pid_file.write_text('456\n')
        second = subject.steam_identity(self.home, os.getuid())
        self.assertEqual(first, {'pid': 123, 'start': 100, 'uid': os.getuid()})
        self.assertEqual(second, {'pid': 456, 'start': 200, 'uid': os.getuid()})

    def test_nonnumeric_target_stat_is_rejected(self):
        fields = ['S', '42'] + ['0'] * 17 + ['not-a-start-time']
        (self.target / 'stat').write_text('123 (steam) ' + ' '.join(fields) + '\n')
        with self.assertRaisesRegex(RuntimeError, 'running Steam client'):
            subject.steam_identity(self.home, os.getuid())

    def test_missing_or_invalid_pid_file_preserves_error(self):
        self.pid_file.write_text('not-a-pid')
        with self.assertRaises(ValueError):
            subject.steam_identity(self.home, os.getuid())
        self.pid_file.unlink()
        with self.assertRaises(FileNotFoundError):
            subject.steam_identity(self.home, os.getuid())


if __name__ == '__main__':
    unittest.main()
