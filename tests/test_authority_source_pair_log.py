"""Final pair-log contract; uses only small temporary files, no X4."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import authority_source_pair_log as pair_log


class SourcePairLogTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'engine.log'

    def read(self, content):
        self.path.write_bytes(content)
        return pair_log.read_source_pair_log(self.path)

    def test_missing_unavailable_and_estimate_are_distinct(self):
        self.assertEqual(self.read(b'other log\n'), {'status': 'missing'})
        prefix = b'[=ERROR=] 3.01 [X4LAN] AUTH_LOCAL_PAIR'
        self.assertEqual(self.read(prefix + b' unavailable\n'), {'status': 'unavailable'})
        self.assertEqual(self.read(prefix + b' estimated dt=0.2 vx=-1e1 vy=0 vz=+.5\n'),
                         {'status': 'estimated', 'dt': .2, 'vx': -10., 'vy': 0., 'vz': .5})

    def test_incomplete_duplicate_and_unrecognized_messages_fail(self):
        tag = pair_log.TAG
        for content in (b'other log', tag + b' unavailable',
                        tag + b' unavailable\n' + tag + b' unavailable\n',
                        tag + b' unavailable ' + tag + b' unavailable\n',
                        tag + b' unexpected\n', tag + b'X\n',
                        tag + b' estimated dt=.2 vx=1 vy=2 vz=3 extra\n'):
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    self.read(content)

    def test_numeric_bounds_and_nonfinite_values(self):
        tag = pair_log.TAG + b' estimated dt='
        for value in (b'.019', b'1.0001', b'1e999', b'nan', b'inf'):
            with self.subTest(elapsed=value):
                with self.assertRaises(ValueError):
                    self.read(tag + value + b' vx=1 vy=2 vz=3\n')
        for value in (b'5000.1', b'-5000.1', b'1e999', b'nan'):
            with self.subTest(velocity=value):
                with self.assertRaises(ValueError):
                    self.read(tag + b'.2 vx=' + value + b' vy=2 vz=3\n')
        self.assertEqual(self.read(tag + b'.02 vx=5000 vy=-5000 vz=0\n')['status'], 'estimated')
        self.assertEqual(self.read(tag + b'1 vx=0 vy=0 vz=0\n')['status'], 'estimated')

    def test_missing_file_symlink_and_changed_identity_are_errors(self):
        with self.assertRaises(FileNotFoundError):
            pair_log.read_source_pair_log(self.path)
        original = self.path.with_name('original')
        original.write_bytes(b'other log\n')
        self.path.symlink_to(original)
        with self.assertRaises(OSError):
            pair_log.read_source_pair_log(self.path)
        self.path.unlink()
        self.path.write_bytes(b'other log\n')
        real_read = pair_log._read_final_regular_file

        def replace_after_read(path):
            result = real_read(path)
            path.unlink()
            path.write_bytes(b'other log\n')
            return result

        with patch.object(pair_log, '_read_final_regular_file', side_effect=replace_after_read):
            with self.assertRaises(ValueError):
                pair_log.read_source_pair_log(self.path)

    def test_fifo_without_writer_is_rejected_without_blocking(self):
        os.mkfifo(self.path)
        script = (
            'import sys; from pathlib import Path; '
            'sys.path.insert(0, "tools/dev"); '
            'import authority_source_pair_log as p; '
            'p.read_source_pair_log(Path(sys.argv[1]))'
        )
        result = subprocess.run([sys.executable, '-B', '-c', script, str(self.path)],
                                cwd=ROOT, capture_output=True, timeout=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'ValueError: invalid final pair log file', result.stderr)

    def test_bounded_reader_rejects_oversize(self):
        self.path.write_bytes(b'x' * 65 + b'\n')
        with patch.object(pair_log, 'MAX_LOG_BYTES', 64):
            with self.assertRaises(ValueError):
                pair_log.read_source_pair_log(self.path)


if __name__ == '__main__':
    unittest.main()
