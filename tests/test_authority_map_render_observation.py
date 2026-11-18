"""Offline contract checks for the read-only map renderer snapshot."""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MapRenderObservation(unittest.TestCase):
    def test_snapshot_contract(self):
        subprocess.run(
            ['luajit', 'tests/authority_map_render_observation.lua'],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )


if __name__ == '__main__':
    unittest.main()
