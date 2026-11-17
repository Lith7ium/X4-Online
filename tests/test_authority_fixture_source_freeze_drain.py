"""Exercise the actual Lua source session with a simulated asynchronous X4 reader."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FixtureSourceFreezeDrain(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_inflight_drain_and_timeout(self):
        subprocess.run(['luajit', 'tests/authority_fixture_source_freeze_drain.lua'],
                       cwd=ROOT, check=True, timeout=10)
