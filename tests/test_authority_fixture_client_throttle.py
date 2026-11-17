"""Synthetic owner and XML checks; no process, real MD or native X4."""
from pathlib import Path
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class FixtureClientThrottleTest(unittest.TestCase):
    def test_cue_well_formed(self):
        ET.parse(ROOT / 'tools/dev/authority_fixture_client_throttle.xml')

    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_owner_fencing(self):
        subprocess.run(['luajit', 'tests/authority_fixture_client_throttle.lua'],
                       cwd=ROOT, check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
