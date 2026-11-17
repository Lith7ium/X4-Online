"""Offline native-ABI simulation, not a real X4 setter test."""
from pathlib import Path
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class LocalOffsetTest(unittest.TestCase):
    def test_cue_is_well_formed(self):
        ET.parse(ROOT / 'tools/dev/authority_fixture_local_offset.xml')

    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_native_abi_and_fences(self):
        subprocess.run(['luajit', 'tests/authority_fixture_local_offset.lua'],
                       cwd=ROOT, check=True, timeout=10)
