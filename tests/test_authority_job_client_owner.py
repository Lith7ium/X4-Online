"""Offline client-owner logic with the real serial Lua client; no X4 launch."""
from pathlib import Path
import subprocess
import os
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ClientOwner(unittest.TestCase):
    def test_correlated_apply_and_fail_closed(self):
        subprocess.run(['luajit','tests/authority_job_client_owner.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)

    def test_real_x4_factory_with_fake_native_abi(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_running_owner_abi.c'),'-o',str(lib)],check=True,capture_output=True)
            for pause in ('0','1'):
                subprocess.run(['luajit','tests/authority_job_client_owner_x4.lua'],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib),TEST_GUARD_PAUSE=pause),check=True,capture_output=True,text=True,timeout=5)
