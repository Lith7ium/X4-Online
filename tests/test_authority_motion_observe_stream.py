"""Exercise bounded observation via real Lua owner/setter; never starts X4."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ObserveStreamTest(unittest.TestCase):
    def test_owner_and_setter(self):
        subprocess.run(['luajit', 'tests/authority_motion_observe_stream.lua'], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=5)

if __name__ == '__main__':
    unittest.main()
