"""Offline Lua and fake-ABI verification; never starts X4."""
import os, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class PlayerSectorInterest(unittest.TestCase):
 def test_state_machine(self):
  subprocess.run(['luajit','tests/authority_player_sector_interest.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
 def test_x4_fake_abi(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'abi.so'
   subprocess.run(['cc','-shared','-fPIC','-O2','tests/fixtures/player_sector_interest_abi.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True)
   subprocess.run(['luajit','tests/authority_player_sector_interest_x4.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5,env=dict(os.environ,LD_PRELOAD=str(lib)))
if __name__=='__main__':unittest.main()
