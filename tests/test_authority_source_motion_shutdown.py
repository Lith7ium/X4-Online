"""Offline source shutdown gate; no native X4 process."""
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
class ShutdownTests(unittest.TestCase):
 def test_real_lua_components_and_fences(self):
  subprocess.run(['luajit','tests/authority_source_motion_shutdown.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
  subprocess.run(['luajit','tests/authority_source_motion_shutdown_stop.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
if __name__=='__main__':unittest.main()
