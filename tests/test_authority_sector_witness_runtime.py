"""Read-only sector witness; synthetic tests only."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
class Witness(unittest.TestCase):
 def test_md_readonly_unique_and_registry_guard(self):
  root=ET.parse(ROOT/'tools/dev/authority_sector_witness_runtime.xml').getroot()
  self.assertEqual({n.tag for n in root.iter()},{'mdscript','cues','cue','conditions','event_ui_triggered','actions','set_value','find_sector','do_if','do_else','raise_lua_event'})
  guards=' '.join(n.get('value','') for n in root.iter('do_if'))
  for s in ('$matches.count == 1','$ship.sector == $matches.{1}','State.$byship.{$ship} == $index','not $ship.dock.exists','not $ship.isinternallystored'):self.assertIn(s,guards)
 @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
 def test_callback_guards(self):
  subprocess.run(['luajit','tests/authority_sector_witness_runtime.lua'],cwd=ROOT,check=True,capture_output=True,timeout=5)
 @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'),'compiler and LuaJIT required')
 def test_fake_ffi_and_large_id(self):
  with tempfile.TemporaryDirectory() as t:
   lib=Path(t)/'fake.so';subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_paused_job_descriptor_fake_x4.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
   subprocess.run(['luajit','tests/authority_sector_witness_runtime_fake_x4.lua',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=5)
