"""Synthetic registry adapter contract; no X4 or network is started."""
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ShipRegistryClientTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_callback_order_identity_timeout_and_fail_closed(self):
        subprocess.run(['luajit', 'tests/authority_ship_registry_client.lua'],
                       cwd=ROOT, check=True, capture_output=True, text=True, timeout=5)
