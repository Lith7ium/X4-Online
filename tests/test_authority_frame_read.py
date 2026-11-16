"""Paused local frame read using fake X4 ABI and simulated MD events."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
class FrameRead(unittest.TestCase):
 def test_read_only_correlated_md(self):
  root=ET.parse(ROOT/'tools/dev/authority_frame_read.xml').getroot()
  self.assertEqual({n.tag for n in root.iter()},{'mdscript','cues','cue','conditions','event_ui_triggered','actions','set_value','do_if','do_else','do_all','find_sector','find_station','raise_lua_event'})
  self.assertTrue(all(n.get('name','').startswith('$') for n in root.iter('set_value')))
  station=root.find('.//find_station');self.assertEqual(station.get('space'),'$sector');self.assertEqual(station.get('multiple'),'true')
 def test_local_paused_guards_and_pinned_codes(self):
  with tempfile.TemporaryDirectory() as d:
   lib=Path(d)/'x4.so'
   subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/authority_frame_read_fake_x4.c'),'-o',str(lib)],check=True,capture_output=True)
   for mode in ('normal','paused','clock','marker','duplicate','wrongcode','wrongmacro','bad_done','reentrant'):
    with self.subTest(mode=mode):
     subprocess.run(['luajit','tests/authority_frame_read.lua',mode],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib)),check=True,capture_output=True,text=True,timeout=5)
