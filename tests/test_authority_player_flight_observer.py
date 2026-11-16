from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class PlayerFlightObserverTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_state_deadlines_and_samples(self):
        subprocess.run(['luajit','tests/authority_player_flight_observer.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'),'LuaJIT and compiler required')
    def test_real_observer_over_fake_x4_abi(self):
        with tempfile.TemporaryDirectory() as d:
            lib=Path(d)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_player_flight_fake_x4.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
            for mode in ('normal','rogue','owner','actor','zone','nan','zone_lost','occupied_lost','container_lost','external_lost'):
                subprocess.run(['luajit','tests/authority_player_flight_observer_x4.lua',str(lib),mode],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
