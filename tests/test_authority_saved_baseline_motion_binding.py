"""Offline saved-baseline binding checks; no X4 process or network."""
from pathlib import Path
import os, subprocess, tempfile, unittest, xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

class SavedBaselineMotionBinding(unittest.TestCase):
 def test_local_x4_binding_and_fences(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/replica_motion_binding_abi.c'),'-o',str(lib)],check=True,capture_output=True)
   for mode in ('ok','bad_index','direct_without_guard','pre_guard','guard','zone','dock','pause','despawn','mutate','stale','unavailable','old_event'):
    with self.subTest(mode=mode):
     subprocess.run(['luajit','tests/authority_saved_baseline_motion_binding.lua'],cwd=ROOT,
      env=dict(os.environ,LD_PRELOAD=str(lib),TEST_BIND_FAILURE=mode),check=True,capture_output=True,text=True,timeout=5)
 def test_separate_read_only_md_screen_preserves_create_receipt_gate(self):
  root=ET.parse(ROOT/'tools/dev/authority_saved_baseline_motion_bind.xml').getroot()
  self.assertEqual(root.get('name'),'X4AuthoritySavedBaselineMotionBind')
  text=ET.tostring(root,encoding='unicode')
  for value in ('State.$byship','State.$ships','State.$epoch','State.$faulted','$r.$baseline','isoperational','isclass.ship','dock.exists','isinternallystored','sector.macro.id','request_id'):
   self.assertIn(value,text)
  self.assertNotIn('MultiCreateReceiver',text)
  for node in root.findall('.//set_value'):self.assertTrue(node.get('name').startswith('$'))
  self.assertFalse(root.findall('.//create_ship'));self.assertFalse(root.findall('.//remove_value'))
  previous=ET.parse(ROOT/'tools/dev/authority_replica_motion_bind.xml').getroot()
  self.assertIn('State.$receipts',ET.tostring(previous,encoding='unicode'))

if __name__=='__main__':unittest.main()
