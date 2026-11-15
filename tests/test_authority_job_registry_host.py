"""Synthetic host event ordering only; no X4 process is started."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class JobRegistryHostTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_status_enrollment_normalization_and_no_events(self):
        subprocess.run(['luajit', 'tests/authority_job_registry_host.lua'], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=5)

    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_attach_saved_registry_without_reset(self):
        subprocess.run(['luajit', 'tests/authority_job_registry_attach.lua'], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=5)

    @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'), 'C compiler and LuaJIT required')
    def test_x4_adapter_normalizes_event_value_before_baseline_enroll(self):
        with tempfile.TemporaryDirectory() as directory:
            library = pathlib.Path(directory) / 'fake-x4.so'
            subprocess.run(['cc', '-shared', '-fPIC', 'tests/lua/authority_npc_source_fake_x4.c',
                            '-o', str(library)], cwd=ROOT, check=True, capture_output=True, timeout=10)
            subprocess.run(['luajit', 'tests/authority_job_registry_x4_fake.lua', str(library)],
                           cwd=ROOT, check=True, capture_output=True, text=True, timeout=5)
