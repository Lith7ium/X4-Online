"""Synthetic subprocess coverage for native runner log collection; no X4."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import linux_gate_live as live
from linux_view_component_trace_evidence import collect_component_trace


@unittest.skipUnless(sys.platform == 'linux', 'Linux runner uses POSIX log aliases')
class GameStreamTests(unittest.TestCase):
    def exercise(self, recurring):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stdout_path = root / 'game1-stdout.log'
            source = live.prepare_game_stderr_log(root, 1, recurring)
            script = "import sys; print('stdout evidence', flush=True); print('stderr evidence', file=sys.stderr, flush=True)"
            with stdout_path.open('wb') as out:
                if source is None:
                    subprocess.run([sys.executable, '-c', script], stdout=out,
                                   stderr=subprocess.STDOUT, check=True)
                else:
                    with source.open('wb') as err:
                        subprocess.run([sys.executable, '-c', script], stdout=out, stderr=err, check=True)
            result_path = root / 'game1-stderr.log'
            data = result_path.read_bytes()
            self.assertIn(b'stderr evidence', data)
            self.assertIn(b'stdout evidence', stdout_path.read_bytes())
            self.assertEqual(result_path.is_symlink(), not recurring)
            if not recurring:
                self.assertIn(b'stdout evidence', data)
                self.assertEqual(data, stdout_path.read_bytes())
            else:
                self.assertNotIn(b'stdout evidence', data)
            proof = collect_component_trace(result_path, None, None, None, False)
            self.assertTrue(proof['pass'], proof)
            self.assertEqual(proof['stderr_sha256'], hashlib.sha256(data).hexdigest())
            with result_path.open('ab') as stream:
                stream.write(b'X4 COMPONENT_TRACE unexpected disabled evidence\n')
            proof = collect_component_trace(result_path, None, None, None, False)
            self.assertFalse(proof['pass'])
            self.assertIn('unexpected disabled component trace receipt', proof['errors'])

    def test_combined_non_recurring_stream_is_visible_to_collectors(self):
        self.exercise(False)

    def test_recurring_streams_stay_separate_and_complete(self):
        self.exercise(True)

    def test_existing_log_alias_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = root / 'game1-stderr.log'
            prior.write_bytes(b'preserve')
            with self.assertRaises(FileExistsError):
                live.prepare_game_stderr_log(root, 1, False)
            self.assertEqual(prior.read_bytes(), b'preserve')


if __name__ == '__main__':
    unittest.main()
