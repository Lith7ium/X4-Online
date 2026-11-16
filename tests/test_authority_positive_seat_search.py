"""Synthetic diagnostics, never an X4 or multiplayer test."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class SearchTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_state_and_fencing(self):
        subprocess.run(['luajit','tests/authority_positive_seat_search.lua'],cwd=ROOT,
                       check=True,capture_output=True,text=True,timeout=5)

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'),'LuaJIT and compiler required')
    def test_fake_x4_adapter(self):
        with tempfile.TemporaryDirectory() as d:
            lib=Path(d)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_positive_seat_fake_x4.c','-o',str(lib)],
                           cwd=ROOT,check=True,capture_output=True,timeout=10)
            subprocess.run(['luajit','tests/authority_positive_seat_search_x4.lua',str(lib)],cwd=ROOT,
                           check=True,capture_output=True,text=True,timeout=5)
