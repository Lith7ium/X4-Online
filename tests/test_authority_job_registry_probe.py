"""Synthetic queue/register callback contract; no X4 or network is started."""
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class JobRegistryProbeTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_ordering_identity_queue_faults_and_limited_classification(self):
        subprocess.run(['luajit', 'tests/authority_job_registry_probe.lua'], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=5)
