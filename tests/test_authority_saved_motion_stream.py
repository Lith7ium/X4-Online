"""The stream is a fake-engine orchestration test, never an X4 start."""
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class SavedMotionStream(unittest.TestCase):
 def test_actual_binding_and_one_shot_state_machines_with_fake_callbacks(self):
  subprocess.run(['luajit','tests/authority_saved_motion_stream.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
if __name__=='__main__':unittest.main()
