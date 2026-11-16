"""Bounded selector: actual Lua and fake local X4 ABI/MD, never X4."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

class RegistryMotionCandidate(unittest.TestCase):
 def test_md_is_well_formed_and_read_only(self):
  root=ET.parse(ROOT/'tools/dev/authority_registry_motion_candidate.xml').getroot()
  for node in root.iter('set_value'):
   self.assertTrue(node.attrib['name'].startswith('$'))
  self.assertFalse(list(root.iter('create_ship')))
 def test_md_excludes_each_player_reference_structurally(self):
  root=ET.parse(ROOT/'tools/dev/authority_registry_motion_candidate.xml').getroot()
  checks=[e.attrib['value'] for e in root.iter('do_if') if '$ship.isoperational' in e.attrib.get('value','')]
  self.assertEqual(len(checks),1)
  clauses=[s.strip() for s in checks[0].split(' and ')]
  for ref in ('player.ship','player.occupiedship','player.container'):
   with self.subTest(reference=ref):self.assertIn('$ship != '+ref,clauses)
 @unittest.skipUnless(os.name=='posix' and shutil.which('cc') and shutil.which('luajit'),'LuaJIT and C compiler required')
 def test_live_fences_and_inconclusive_paths(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'abi.so'
   subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/replica_motion_binding_abi.c'),'-o',str(lib)],check=True,capture_output=True)
   for mode in ('ok','skip','none','docked','nil_getter','throw_getter','changing_dock','wrong_macro','refused','stale','guard','guard_overrun','pause','timeout','reentrant','wrong_sector','malformed'):
    with self.subTest(mode=mode):
     subprocess.run(['luajit','tests/authority_registry_motion_candidate.lua',mode],cwd=ROOT,check=True,capture_output=True,timeout=5,env=dict(os.environ,LD_PRELOAD=str(lib)))

if __name__=='__main__':unittest.main()
