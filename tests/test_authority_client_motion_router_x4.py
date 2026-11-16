"""Client router and actual Lua binders with a fake X4 ABI/MD."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class RoutedClient(unittest.TestCase):
 @unittest.skipUnless(os.name=='posix' and shutil.which('cc') and shutil.which('luajit'),'LuaJIT and C compiler required')
 def test_fresh_owner_and_stale_events(self):
  with tempfile.TemporaryDirectory() as tmp:
   abi=Path(tmp)/'fake.so'
   subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/replica_motion_binding_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
   for mode in ('good','stale','stale_same','guard','router_guard','tamper'):
    with self.subTest(mode=mode):
     subprocess.run(['luajit','tests/authority_client_motion_router_x4.lua',mode],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5,env=dict(os.environ,LD_PRELOAD=str(abi)))
if __name__=='__main__':unittest.main()
