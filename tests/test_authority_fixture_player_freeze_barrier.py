"""Offline asynchronous freeze/drain contract, no X4 or UDP."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FixturePlayerFreezeBarrierTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_asynchronous_drain_and_failure_fences(self):
        subprocess.run(['luajit', 'tests/authority_fixture_player_freeze_barrier.lua'],
                       cwd=ROOT, check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
