"""Run the opt-in diagnostic with the real Lua wire and motion primitives."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RegistryMotionProbeTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'), 'LuaJIT and C compiler required')
    def test_pause_loss_fences_native_calls_and_outstanding_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = pathlib.Path(tmp)/'fake-x4.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_motion_fake_x4.c','-o',str(library)],
                           cwd=ROOT,check=True,capture_output=True,text=True,timeout=10)
            subprocess.run(['luajit','tests/lua/authority_registry_motion_native_pause.lua',str(library)],
                           cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)

    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_registry_to_velocity_wire_to_guarded_client_write(self):
        subprocess.run(['luajit', 'tests/authority_registry_motion_probe.lua'],
                       cwd=ROOT, check=True, capture_output=True, text=True, timeout=5)
