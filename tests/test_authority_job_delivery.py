"""Offline only: no X4, transport, or listener starts."""
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class JobDeliveryTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_multi_client_delivery_gate(self):
        subprocess.run(['luajit', 'tests/authority_job_delivery.lua'], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=5)
