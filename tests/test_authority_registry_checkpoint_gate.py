import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
class RegistryCheckpointGateTests(unittest.TestCase):
    def test_full_capture_gate_and_failure_fences(self):
        subprocess.run(
            ['luajit', 'tests/authority_registry_checkpoint_gate.lua'],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )


if __name__ == '__main__':
    unittest.main()
