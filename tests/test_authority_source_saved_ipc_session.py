"""Explicit saved registration through the real local Lua session/IPC."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class SourceSavedIPC(unittest.TestCase):
 def test_registration_receipt_after_sampler_and_guards(self):
  with tempfile.TemporaryDirectory() as d:
   lib=Path(d)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_running_owner_abi.c'),'-o',str(lib)],check=True,capture_output=True)
   for scenario in ('normal','range','baseline','foreign','guard','register_fail','postcheck','timeout','pending_packet','pending_register','deadline_response'):
    with self.subTest(scenario=scenario):
     subprocess.run(['luajit','tests/authority_source_saved_ipc_session.lua',scenario],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib)),check=True,capture_output=True,text=True,timeout=5)
