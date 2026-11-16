"""Synthetic state-machine and fake native binding, never runs X4."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
class CensusOwner(unittest.TestCase):
 def test_client_baseline_is_read_only(self):
  root=ET.parse(ROOT/'tools/dev/authority_census_job_baseline.xml').getroot()
  self.assertEqual({n.tag for n in root.iter()},{'mdscript','cues','cue','conditions','event_ui_triggered','actions','set_value','do_if','do_else','raise_lua_event'})
  guard=' '.join(n.get('value','') for n in root.iter('do_if'))
  for part in ('State.$last == 10054','not md.X4AuthorityShipRegistry.State.$faulted','State.$epoch == $v.$epoch','State.$ships?','State.$byship?'):self.assertIn(part,guard)

 @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
 def test_state_and_fault_paths(self):
  subprocess.run(['luajit','tests/authority_census_job_owner.lua'],cwd=ROOT,check=True,capture_output=True,timeout=5)
 @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'),'compiler and LuaJIT required')
 def test_fake_x4_binding(self):
  with tempfile.TemporaryDirectory() as t:
   lib=Path(t)/'fake.so';subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_paused_job_descriptor_fake_x4.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
   subprocess.run(['luajit','tests/authority_census_job_owner_fake_x4.lua',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=5)
