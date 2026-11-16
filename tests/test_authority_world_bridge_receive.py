"""Control-owner malformed UDP and delayed marker fencing; X4 is simulated."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
class WorldBridgeReceiveTests(unittest.TestCase):
    def test_receive_fences_malformed_datagrams_and_late_marker(self):
        modes = ('good', 'empty', 'oversize', 'race_empty', 'race_oversize',
                 'pending_error', 'marker_empty', 'marker_oversize',
                 'marker_queued_empty', 'marker_queued_oversize',
                 'marker_before_callback_empty', 'marker_before_callback_oversize',
                 'marker_before_callback_pending_error', 'marker_callback_clock_error')
        for mode in modes:
            with self.subTest(mode=mode):
                subprocess.run(['luajit', 'tests/authority_world_bridge_receive.lua', mode],
                               cwd=ROOT, check=True, capture_output=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
