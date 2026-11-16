"""One-shot local writer and owner use fake X4 ABI; no native X4 process."""
from pathlib import Path
import os, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
class SavedMotionApply(unittest.TestCase):
    def test_owner_and_writer_fences(self):
        subprocess.run(['luajit','tests/authority_saved_motion_apply.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
    def test_x4_abi_position_and_radian_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            abi=Path(tmp)/'fake.so'
            subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/saved_motion_apply_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
            for script in ('authority_saved_motion_apply_x4.lua','authority_saved_motion_apply_full_x4.lua'):
                with self.subTest(script=script):
                    subprocess.run(['luajit','tests/'+script],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5,env=dict(os.environ,LD_PRELOAD=str(abi)))
