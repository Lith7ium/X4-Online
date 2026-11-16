"""Offline synthetic owner tests. No X4 is started."""
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
class MotionCalibration(unittest.TestCase):
 def test_real_buffer_and_fake_callbacks(self):
  for mode in ('ok','unsafe_before','actor_change','parent_change','stationary_game_clock','unknown_rate',
               'unknown_later','dispatch_exception','guard_loss_after_dispatch','slow_dispatch','real_clock_reverse',
               'game_clock_reverse','nan_position','nil_ack','wrong_ack','timeout','duplicate_ack','delayed_first','report_guard_loss'):
   with self.subTest(mode=mode):
    result=subprocess.run(['luajit','tests/authority_motion_calibration_offline.lua',mode],cwd=ROOT,capture_output=True,text=True,timeout=5)
    self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
