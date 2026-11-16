"""Linux fake C ABI, not a native X4 or shared-world test."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class InspectorABI(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'), 'C compiler and LuaJIT required')
    def test_fake_x4_abi_and_uint64_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_fake_abi.c'),'-o',str(lib)],check=True,capture_output=True)
            env=dict(os.environ,LD_PRELOAD=str(lib))
            subprocess.run(['luajit','tests/authority_multi_create_inspector.lua'],cwd=ROOT,env=env,check=True,capture_output=True,text=True,timeout=10)

if __name__=='__main__':unittest.main()
