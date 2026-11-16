from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class LiveOwnerTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'),'LuaJIT and compiler required')
    def test_local_owner_over_fake_x4(self):
        with tempfile.TemporaryDirectory() as d:
            lib=Path(d)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_player_control_fake_x4.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
            for mode in ('controlled','inconclusive','timeout','bad_nonce','rogue','relapse','npc_lost'):
                subprocess.run(['luajit','tests/authority_player_control_live_x4.lua',str(lib),mode],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
