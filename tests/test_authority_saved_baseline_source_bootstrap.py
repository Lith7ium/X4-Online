"""Local bootstrap uses real Lua/FFI path with simulated MD, no X4 start."""
import os, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SavedBaselineSourceBootstrap(unittest.TestCase):
 def test_local_correlation_and_runtime_fences(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_running_owner_abi.c'),'-o',str(lib)],check=True,capture_output=True)
   for mode in ('ok','invalid_index','foreign','wrong_index','wrong_actor','wrong_sector','wrong_macro','dock','guard','pause','timeout','unavailable','reentrant','post_dock','post_guard'):
    with self.subTest(mode=mode):
     subprocess.run(['luajit','tests/authority_saved_baseline_source_bootstrap.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5,
      env=dict(os.environ,LD_PRELOAD=str(lib),BOOTSTRAP_CASE=mode))
if __name__=='__main__':unittest.main()
