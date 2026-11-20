import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
class AvailabilitySnapshotOwnerTests(unittest.TestCase):
    def test_full_snapshot_owner(self):
        subprocess.run(
            ['luajit', 'tests/authority_registry_availability_snapshot_owner.lua'],
            cwd=ROOT,
            check=True,
        )


if __name__ == '__main__':
    unittest.main()
