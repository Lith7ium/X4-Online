"""Local comparison observer contracts; no X4 or native event coverage implied."""
from pathlib import Path
import subprocess
import tempfile
import os
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
class Compare(unittest.TestCase):
 def test_lua_exact_identity_and_fencing(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC',str(ROOT/'tests/fixtures/ship_event_compare_fake_abi.c'),'-o',str(lib)],check=True,capture_output=True)
   subprocess.run(['luajit','tests/authority_ship_event_compare.lua'],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib)),check=True,capture_output=True,timeout=5)
 def test_md_is_read_only_and_preserves_event_provenance(self):
  r=ET.parse(ROOT/'tools/dev/authority_ship_event_compare.xml').getroot()
  self.assertEqual(r.get('name'),'X4AuthorityShipEventCompare')
  self.assertEqual([len(r.findall('.//'+x)) for x in ('event_god_created_ship','event_player_built_ship','event_job_ship_activated','event_object_entered')],[1,1,1,1])
  enter=r.find('.//event_object_entered');self.assertEqual(enter.get('space'),'player.galaxy')
  self.assertFalse(r.findall('.//create_ship'))
  text=ET.tostring(r,encoding='unicode')
  self.assertNotIn("control=\"'Enroll'\"",text)
  for node in r.iter():
   if node.tag in ('set_value','remove_value'):
    self.assertNotIn('X4AuthorityShipRegistry',node.get('name',''))
  for label in ("'god'","'player_build'","'activation'","'galaxy_enter'","'capture_or_overflow'","'registry_binding'"):
   self.assertIn(label,text)
