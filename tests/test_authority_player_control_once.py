from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class PlayerControlOnceTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_one_shot_state_machine(self):
        subprocess.run(['luajit','tests/authority_player_control_once.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'),'LuaJIT and compiler required')
    def test_fake_x4_local_independent_readbacks(self):
        with tempfile.TemporaryDirectory() as d:
            lib=Path(d)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_player_control_fake_x4.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
            for mode in ('normal','wrong_before','owner_changed','wrong_after'):
                subprocess.run(['luajit','tests/authority_player_control_once_x4.lua',str(lib),mode],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
