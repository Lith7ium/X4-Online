"""Offline coverage of the optional saved-apply route; does not start X4."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SavedApplyRouterTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_routing_and_fences(self):
        subprocess.run(['luajit', 'tests/authority_client_motion_apply_router.lua'],
                       cwd=ROOT, check=True, capture_output=True, text=True, timeout=5)

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'), 'LuaJIT and C compiler required')
    def test_real_lua_owners_with_fake_x4_abi(self):
        with tempfile.TemporaryDirectory() as temporary:
            abi = Path(temporary) / 'fake_x4.so'
            subprocess.run(['cc', '-O2', '-shared', '-fPIC',
                            'tests/fixtures/saved_motion_apply_abi.c', '-o', str(abi)],
                           cwd=ROOT, check=True, capture_output=True)
            environment = dict(os.environ, LD_PRELOAD=str(abi))
            subprocess.run(['luajit', 'tests/authority_client_motion_apply_router_x4.lua'],
                           cwd=ROOT, env=environment, check=True,
                           capture_output=True, text=True, timeout=5)
