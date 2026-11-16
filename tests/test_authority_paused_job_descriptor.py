"""Offline paused job-descriptor probes; never runs X4."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
class PausedJob(unittest.TestCase):
 def test_md_reads_only_and_excludes_docked(self):
  root=ET.parse(ROOT/'tools/dev/authority_paused_job_descriptor.xml').getroot()
  self.assertEqual({n.tag for n in root.iter()},{'mdscript','cues','cue','conditions','event_ui_triggered','actions','set_value','do_if','do_else','raise_lua_event'})
  guard=' '.join(n.get('value','') for n in root.iter('do_if'))
  for s in ('not $ship.dock.exists','not $ship.isinternallystored','@md.X4AuthorityShipRegistry.State.$byship.{$ship} == $index'):self.assertIn(s,guard)
 @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
 def test_callback_failure_paths(self):
  subprocess.run(['luajit','tests/authority_paused_job_descriptor.lua'],cwd=ROOT,check=True,capture_output=True,timeout=5)
 @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'),'C compiler and LuaJIT required')
 def test_fake_x4_ffi_and_exact_id(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_paused_job_descriptor_fake_x4.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
   subprocess.run(['luajit','tests/authority_paused_job_descriptor_fake_x4.lua',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=5)
