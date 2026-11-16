"""Bounded source motion IPC without X4 or network processes."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class SourceMotionIPC(unittest.TestCase):
 def test_pull_correlation_unknown_velocity_and_fail_closed(self):
  subprocess.run(['luajit','tests/authority_source_motion_ipc.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
if __name__=='__main__':unittest.main()
