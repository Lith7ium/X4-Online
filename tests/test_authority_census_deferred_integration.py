"""Real Lua source components with fake MD and no native game."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeferredSourceIntegration(unittest.TestCase):
    def test_owner_host_probe_gate_with_async_md(self):
        subprocess.run(['luajit', 'tests/authority_census_deferred_integration.lua'],
                       cwd=ROOT, check=True, capture_output=True, text=True, timeout=5)
