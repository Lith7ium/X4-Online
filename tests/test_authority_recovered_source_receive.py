"""Source-owner receive fencing with simulated X4 and UDP; no game start."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'), 'LuaJIT and C compiler required')
class RecoveredSourceReceive(unittest.TestCase):
    def test_invalid_datagrams_and_pending_race(self):
        with tempfile.TemporaryDirectory() as directory:
            abi = Path(directory)/'abi.so'
            subprocess.run(['cc', '-shared', '-fPIC', 'tests/fixtures/replica_motion_binding_abi.c',
                            '-o', str(abi)], cwd=ROOT, check=True, capture_output=True)
            env = dict(os.environ, LD_PRELOAD=str(abi))
            for mode in ('good', 'empty', 'oversize', 'race_empty', 'race_oversize', 'pending_error',
                         'queued_empty', 'queued_oversize', 'late_empty', 'late_oversize', 'pending_error_stopped'):
                with self.subTest(mode=mode):
                    subprocess.run(['luajit', 'tests/authority_recovered_source_receive.lua', mode],
                                   cwd=ROOT, env=env, check=True, capture_output=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
