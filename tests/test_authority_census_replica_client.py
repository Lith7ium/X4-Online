"""Replica client synthetic state/FFI tests, no X4 execution."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class Replica(unittest.TestCase):
 @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
 def test_state_and_failure_paths(self):
  subprocess.run(['luajit','tests/authority_census_replica_client.lua'],cwd=ROOT,check=True,capture_output=True,timeout=5)
 @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'),'compiler and LuaJIT required')
 def test_fake_x4_ffi(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_paused_job_descriptor_fake_x4.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
   subprocess.run(['luajit','tests/authority_census_replica_client_fake_x4.lua',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=5)
