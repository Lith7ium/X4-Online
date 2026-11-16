"""Local read-only test authority; real Lua bootstrap/sampler with fake MD/FFI."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ClientAuthorityMotionReader(unittest.TestCase):
    def test_actual_bootstrap_and_sampler_with_fake_game(self):
        subprocess.run(['luajit','tests/authority_client_authority_motion_reader.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
