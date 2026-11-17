"""Offline contract test; this does not start X4 or validate a native write."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FixturePlayerPoseOnceTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_one_shot_and_fences(self):
        subprocess.run(['luajit', 'tests/authority_fixture_player_pose_once.lua'],
                       cwd=ROOT, check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
