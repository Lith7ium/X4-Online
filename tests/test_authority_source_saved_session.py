"""Local bootstrap/session integration with a fake X4 ABI, no game launch."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class SourceSavedSession(unittest.TestCase):
 def test_bootstrap_staging_and_fences(self):
  with tempfile.TemporaryDirectory() as d:
   lib=Path(d)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_running_owner_abi.c'),'-o',str(lib)],check=True,capture_output=True)
   for scenario in ('normal','collision','foreign','guard','postcheck','next_tick','next_router','guard_tick','guard_router'):
    with self.subTest(scenario=scenario):
     subprocess.run(['luajit','tests/authority_source_saved_session.lua',scenario],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib)),check=True,capture_output=True,text=True,timeout=5)
