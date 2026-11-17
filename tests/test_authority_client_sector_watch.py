"""Bounded local log observation tests; no X4 or network."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
from authority_client_sector_watch import ClientSectorLogWatch


class ClientSectorLogWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'engine-output.log'
        self.watch = ClientSectorLogWatch(self.path)
        self.tag = b'[X4LAN] AUTH_CLIENT_SECTOR'

    def append(self, data):
        with self.path.open('ab') as log:
            log.write(data)

    def test_split_marker_and_confirmed_final_log(self):
        self.watch.poll()  # The client has not created its log yet.
        self.append(b'[=ERROR=] 1.0 [X4LAN] AUTH_CLIENT_')
        self.watch.poll()
        self.append(b'SECTOR observed sector=cluster_14_sector001_macro\n')
        self.watch.poll()
        self.watch.confirm_stop(confirmed=True)
        self.append(b'[General] process shutting down\n')
        self.assertEqual(self.watch.finish(process_stopped=True), 'cluster_14_sector001_macro')
        with self.assertRaises(ValueError):
            self.watch.poll()

    def test_bounded_polls_require_catching_up_before_stop(self):
        self.path.write_bytes(self.tag + b' observed sector=sector_a\n')
        with patch.object(ClientSectorLogWatch, 'MAX_POLL_BYTES', 8):
            self.assertFalse(self.watch.poll())
            while not self.watch.poll():
                pass
            self.watch.confirm_stop(confirmed=True)
            self.assertEqual(self.watch.finish(process_stopped=True), 'sector_a')
            watch = ClientSectorLogWatch(self.path)
            with self.assertRaisesRegex(ValueError, 'not caught up'):
                watch.confirm_stop(confirmed=True)

    def test_observe_requires_complete_caught_up_line_and_is_provisional(self):
        self.assertIsNone(self.watch.observe())
        self.path.write_bytes(self.tag + b' observed sector=sector_a')
        self.assertIsNone(self.watch.observe())
        self.append(b'\nother line\n')
        with patch.object(ClientSectorLogWatch, 'MAX_POLL_BYTES', 1):
            self.assertIsNone(self.watch.observe())
            while self.watch.observe() is None:
                pass
        self.assertEqual(self.watch.observe(), 'sector_a')
        self.append(self.tag + b' observed sector=sector_a\n')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.watch.observe()
        with self.assertRaises(ValueError):
            self.watch.observe()

    def test_disarmed_rejects_complete_and_fragmented_early_marker(self):
        marker = self.tag + b' observed sector=sector_a\n'
        self.path.write_bytes(marker)
        watch = ClientSectorLogWatch(self.path, disarmed=True)
        with self.assertRaisesRegex(ValueError, 'before arming'):
            watch.poll()
        with self.assertRaises(ValueError):
            watch.arm()

        self.path.write_bytes(marker[:15])
        watch = ClientSectorLogWatch(self.path, disarmed=True)
        self.assertTrue(watch.poll())
        self.append(marker[15:-1])  # Complete tag without a terminating newline.
        with self.assertRaisesRegex(ValueError, 'before arming'):
            watch.poll()
        with self.assertRaises(ValueError):
            watch.arm()

    def test_arm_requires_caught_up_log_with_no_partial_line(self):
        watch = ClientSectorLogWatch(self.path, disarmed=True)
        with self.assertRaisesRegex(ValueError, 'not ready'):
            watch.arm()

        self.path.write_bytes(self.tag[:15])
        watch = ClientSectorLogWatch(self.path, disarmed=True)
        with self.assertRaisesRegex(ValueError, 'not ready'):
            watch.arm()
        with self.assertRaises(ValueError):
            watch.arm()

        self.path.write_bytes(b'prior log line\n')
        watch = ClientSectorLogWatch(self.path, disarmed=True)
        with patch.object(ClientSectorLogWatch, 'MAX_POLL_BYTES', 2):
            with self.assertRaisesRegex(ValueError, 'not ready'):
                watch.arm()

    def test_armed_watch_preserves_duplicate_stop_and_final_checks(self):
        self.path.write_bytes(b'prior log line\n')
        watch = ClientSectorLogWatch(self.path, disarmed=True)
        watch.arm()
        self.append(self.tag + b' observed sector=sector_a\n')
        self.assertEqual(watch.observe(), 'sector_a')
        watch.confirm_stop(confirmed=True)
        self.assertEqual(watch.finish(process_stopped=True), 'sector_a')

        self.path.write_bytes(b'prior log line\n')
        watch = ClientSectorLogWatch(self.path, disarmed=True)
        watch.arm()
        self.append((self.tag + b' observed sector=sector_a\n') * 2)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            watch.observe()

        self.path.write_bytes(b'prior log line\n')
        watch = ClientSectorLogWatch(self.path, disarmed=True)
        watch.arm()
        self.append(self.tag + b' observed sector=sector_a\n')
        watch.confirm_stop(confirmed=True)
        self.append(self.tag + b' observed sector=sector_a\n')
        with self.assertRaisesRegex(ValueError, 'late'):
            watch.finish(process_stopped=True)

        self.path.write_bytes(b'prior log line\n')
        watch = ClientSectorLogWatch(self.path, disarmed=True)
        watch.arm()
        with self.assertRaisesRegex(ValueError, 'cannot be armed'):
            watch.arm()
        with self.assertRaises(ValueError):
            watch.observe()

    def test_invalid_duplicate_and_late_markers_fail_closed(self):
        valid = self.tag + b' observed sector=sector_a\n'
        for content in (self.tag + b' observed sector=../bad\n',
                        self.tag + b' observed sector=sector_a extra\n',
                        valid + valid,
                        self.tag + b' observed sector=sector_a ' + self.tag + b'\n'):
            with self.subTest(content=content):
                self.path.write_bytes(content)
                watch = ClientSectorLogWatch(self.path)
                with self.assertRaises(ValueError):
                    watch.poll()
                with self.assertRaises(ValueError):
                    watch.poll()
        self.path.write_bytes(valid)
        watch = ClientSectorLogWatch(self.path)
        watch.confirm_stop(confirmed=True)
        self.append(valid)
        with self.assertRaisesRegex(ValueError, 'late'):
            watch.finish(process_stopped=True)

    def test_final_requires_observation_stop_exit_and_complete_line(self):
        self.path.write_bytes(b'[General] ready\n')
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.watch.confirm_stop(confirmed=True)
        self.path.write_bytes(self.tag + b' observed sector=sector_a\n')
        watch = ClientSectorLogWatch(self.path)
        with self.assertRaises(ValueError):
            watch.confirm_stop(confirmed=False)
        watch = ClientSectorLogWatch(self.path)
        watch.confirm_stop(confirmed=True)
        with self.assertRaises(ValueError):
            watch.finish(process_stopped=False)
        watch = ClientSectorLogWatch(self.path)
        watch.confirm_stop(confirmed=True)
        self.append(b'partial line')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            watch.finish(process_stopped=True)

    def test_split_error_and_oversized_line_are_rejected_without_raw_output(self):
        error = b'Error while executing onEvent script for event: X4AuthorityPlayerSectorInterest.Result.'
        self.append(error[:30])
        self.watch.poll()
        self.append(error[30:])
        with self.assertRaisesRegex(ValueError, 'reported an error') as caught:
            self.watch.poll()
        self.assertNotIn(error.decode(), str(caught.exception))
        self.path.write_bytes(b'x' * (ClientSectorLogWatch.MAX_LINE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'line exceeds'):
            ClientSectorLogWatch(self.path).poll()

    def test_missing_replacement_truncation_and_same_size_rewrite_fail(self):
        self.path.write_bytes(b'first line\n')
        self.watch.poll()
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, 'disappeared'):
            self.watch.poll()
        self.path.write_bytes(b'first line\n')
        watch = ClientSectorLogWatch(self.path)
        watch.poll()
        replacement = self.path.with_name('replacement')
        replacement.write_bytes(b'first line\n')
        replacement.replace(self.path)
        with self.assertRaisesRegex(ValueError, 'replaced'):
            watch.poll()
        watch = ClientSectorLogWatch(self.path)
        watch.poll()
        self.path.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'truncated'):
            watch.poll()
        self.path.write_bytes(b'first line\n')
        watch = ClientSectorLogWatch(self.path)
        watch.poll()
        self.path.write_bytes(b'other line\n')
        with self.assertRaisesRegex(ValueError, 'without appending'):
            watch.poll()

    def test_symlink_and_growth_limits_are_rejected(self):
        target = self.path.with_name('real')
        target.write_bytes(b'line\n')
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            self.watch.poll()
        self.path.unlink()
        self.path.write_bytes(b'long enough\n')
        with patch.object(ClientSectorLogWatch, 'MAX_LOG_BYTES', 4):
            with self.assertRaisesRegex(ValueError, 'invalid client log'):
                ClientSectorLogWatch(self.path).poll()

    @unittest.skipUnless(hasattr(os, 'mkfifo') and getattr(os, 'O_NONBLOCK', 0),
                         'FIFO and nonblocking open required')
    def test_fifo_is_rejected_without_waiting_for_a_writer(self):
        os.mkfifo(self.path)
        script = (
            'import sys; sys.path.insert(0, sys.argv[1]); '
            'from authority_client_sector_watch import ClientSectorLogWatch; '
            'ClientSectorLogWatch(sys.argv[2]).poll()'
        )
        result = subprocess.run([sys.executable, '-c', script, str(ROOT / 'tools/dev'), str(self.path)],
                                capture_output=True, timeout=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'ValueError: invalid client log', result.stderr)


if __name__ == '__main__':
    unittest.main()
