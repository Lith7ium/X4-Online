"""Pure sampler plus real descriptor/X4 factory with fake ABI; never starts X4."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class SourceMotionSampler(unittest.TestCase):
    def test_bounded_sampling_and_failure_fences(self):
        subprocess.run(['luajit','tests/authority_source_motion_sampler.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
    def test_existing_descriptor_and_x4_fake_abi(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_running_owner_abi.c'),'-o',str(lib)],check=True,capture_output=True)
            subprocess.run(['luajit','tests/authority_source_motion_sampler_x4.lua'],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib)),check=True,capture_output=True,text=True,timeout=5)
if __name__=='__main__':unittest.main()
