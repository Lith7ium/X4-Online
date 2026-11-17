"""Offline contract for the opt-in player latest-value cache."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FixturePlayerLatestCacheTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_capture_delivery_and_lifecycle_fences(self):
        subprocess.run(['luajit', 'tests/authority_fixture_player_latest_cache.lua'],
                       cwd=ROOT, check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
