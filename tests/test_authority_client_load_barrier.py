"""Client load barrier state checks; uses no X4 process or real supervisor."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
class ClientLoadBarrierTest(unittest.TestCase):
    def test_barrier_across_simulated_ui_reload(self):
        subprocess.run(['luajit', 'tests/authority_client_load_barrier.lua'], cwd=ROOT, check=True,
                       capture_output=True, text=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
