"""Offline event-router tests; no X4 instance or native game API."""
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class RouterTest(unittest.TestCase):
 @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
 def test_routes_and_fences(self):
  subprocess.run(['luajit','tests/authority_client_motion_event_router.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
if __name__=='__main__':unittest.main()
