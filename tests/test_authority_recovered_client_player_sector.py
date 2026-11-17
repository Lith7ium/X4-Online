"""Read-only sector owner integration with independent simulated clients."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LUAJIT = shutil.which('luajit')


@unittest.skipUnless(LUAJIT, 'LuaJIT is required')
class RecoveredClientPlayerSector(unittest.TestCase):
    def test_isolated_clients_and_failure_fences(self):
        for mode in ('ok', 'cross', 'pending_stop', 'guard', 'guard_reenter', 'mutate', 'reenter', 'late',
                     'factory_failure', 'register_failure'):
            with self.subTest(mode=mode):
                subprocess.run([LUAJIT, 'tests/authority_recovered_client_player_sector.lua', mode],
                               cwd=ROOT, check=True, capture_output=True, text=True, timeout=5)

    @unittest.skipUnless(shutil.which('cc'), 'C compiler is required')
    def test_x4_adapter_and_event_route_with_simulated_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / 'sector-abi.so'
            subprocess.run(['cc', '-shared', '-fPIC', '-O2',
                            'tests/fixtures/recovered_client_sector_abi.c', '-o', str(library)],
                           cwd=ROOT, check=True, capture_output=True)
            subprocess.run([LUAJIT, 'tests/authority_recovered_client_sector_x4.lua'],
                           cwd=ROOT, check=True, capture_output=True, timeout=5,
                           env=dict(os.environ, LD_PRELOAD=str(library)))

    @unittest.skipUnless(shutil.which('cc'), 'C compiler is required')
    def test_single_bind_precedes_sector_query(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / 'motion-abi.so'
            subprocess.run(['cc', '-shared', '-fPIC', '-O2',
                            'tests/fixtures/replica_motion_binding_abi.c', '-o', str(library)],
                           cwd=ROOT, check=True, capture_output=True)
            for mode in ('good', 'wrong_index', 'forged_ack', 'duplicate', 'send_failure', 'failure_after_send',
                         'stop_before_query', 'stop_pending'):
                with self.subTest(mode=mode):
                    subprocess.run([LUAJIT, 'tests/authority_recovered_sector_after_bound.lua', mode],
                                   cwd=ROOT, check=True, capture_output=True, text=True, timeout=5,
                                   env=dict(os.environ, LD_PRELOAD=str(library)))


if __name__ == '__main__':
    unittest.main()
