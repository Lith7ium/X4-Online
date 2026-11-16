"""Actual source session/job/motion state machines with fake X4 ABI; no X4 start."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class Integrated(unittest.TestCase):
 def test_confirmed_job_then_pull_through_single_descriptor_router(self):
  with tempfile.TemporaryDirectory() as d:
   lib=Path(d)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_running_owner_abi.c'),'-o',str(lib)],check=True,capture_output=True)
   for scenario in ('normal','diagnostic','foreign_reason'):
    subprocess.run(['luajit','tests/authority_source_job_motion_integration.lua',scenario],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib)),check=True,capture_output=True,text=True,timeout=5)
if __name__=='__main__':unittest.main()
