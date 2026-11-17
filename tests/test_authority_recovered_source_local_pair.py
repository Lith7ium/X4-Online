"""Offline router/IPC integration with real Lua owners and simulated X4."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LUAJIT = shutil.which('luajit')


@unittest.skipUnless(LUAJIT, 'LuaJIT is required')
class SourceLocalPairIntegrationTest(unittest.TestCase):
    def test_opt_in_pair_preserves_one_normal_pull_response(self):
        for mode in ('ok', 'stop_pending', 'timeout', 'foreign', 'binding_loss', 'frame',
                     'mutate', 'reenter', 'late_active', 'late_stopped'):
            with self.subTest(mode=mode):
                completed = subprocess.run([LUAJIT, 'tests/authority_recovered_source_local_pair.lua', mode],
                                           cwd=ROOT, capture_output=True, text=True, timeout=5)
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_opt_in_pair_delivery_uses_the_second_sample_only(self):
        for mode in ('delivery_ok', 'delivery_duplicate', 'delivery_unavailable',
                     'delivery_frame', 'delivery_actor', 'delivery_late'):
            with self.subTest(mode=mode):
                completed = subprocess.run([LUAJIT, 'tests/authority_recovered_source_local_pair.lua', mode],
                                           cwd=ROOT, capture_output=True, text=True, timeout=5)
                self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == '__main__':
    unittest.main()
