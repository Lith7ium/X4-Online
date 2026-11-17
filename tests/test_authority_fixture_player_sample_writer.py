"""Synthetic tests of the once-only local X4 sample writer; no X4 start."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FixtureSampleWriterTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_local_abi_and_identity_guards(self):
        subprocess.run(['luajit', 'tests/authority_fixture_player_sample_writer.lua'],
                       cwd=ROOT, check=True, timeout=10)
