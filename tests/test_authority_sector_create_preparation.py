"""Synthetic preparation checks; this is not an installable X4 harness."""
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

class PreparationTests(unittest.TestCase):
 def test_receiver_variant_changes_only_sector_resolution(self):
  old=(ROOT/'tools/dev/authority_ship_create_receiver.xml').read_text()
  new=(ROOT/'tools/dev/authority_sector_create_receiver.xml').read_text()
  prefix='      <!-- Only the two stored fixture sectors are admissible in this disposable experiment. -->\n'
  suffix='      <set_value name="$owner" exact="null"/>\n'
  self.assertEqual(new.count(prefix),1);self.assertEqual(new.count(suffix),1)
  before,rest=new.split(prefix);_,after=rest.split(suffix)
  reconstructed=before+'      <set_value name="$sector" exact="@player.sector"/>\n'+suffix+after
  reconstructed=reconstructed.replace('<!-- Test-only receiver variant. Never install alongside the original receiver. -->','<!-- Opt-in disposable experiment. No network listener or gameplay integration. -->')
  self.assertEqual(reconstructed,old)
  root=ET.fromstring(new);find=root.find('.//find_sector');self.assertEqual(find.get('multiple'),'true')
  self.assertTrue(any('$matches.count == 1' in (x.get('value') or '') and '$sector1' in x.get('value') and '$sector2' in x.get('value') for x in root.findall('.//do_if')))
 def test_inspector_guards_baseline_and_readback(self):
  root=ET.parse(ROOT/'tools/dev/authority_sector_create_inspect.xml').getroot()
  conditions='\n'.join(e.get('value','') for e in root.findall('.//do_if'))
  for value in ('$last == 2','not md.X4AuthorityShipCreateReceiver.State.$epoch?', '$index1 == 1','$index2 == 2','$byship','.$receipts','.$macros','.$sectors','.$owners','.$seeds','.$xs','.$ys','.$zs','.$pending == false','$s1 != player.sector or $s2 != player.sector'):
   self.assertIn(value,conditions)
  self.assertFalse(root.findall('.//create_ship'))
 def test_fake_x4_owner_driver_integration(self):
  for mode in ('ok','mismatch'):
   with self.subTest(mode=mode):subprocess.run(['luajit','tests/authority_sector_create_integration.lua',mode],cwd=ROOT,check=True,capture_output=True)
 def test_owner_fake_x4(self):
  for mode in ('ok','disabled','late_event','registration','registration_false','registration_callback','bad_path','unpaused','invalid_actor','invalid_candidate','wrong_sector','pause_during_pose','time_during_pose','nan','fleet_changed','fleet_cut','fleet_duplicate','conversion','bad_macro'):
   with self.subTest(mode=mode):subprocess.run(['luajit','tests/authority_sector_create_owner.lua',mode],cwd=ROOT,check=True,capture_output=True)
 def test_state_machine(self):
  for mode in ('ok','disabled','guard','dispatch','reentrant','bad_count','wrong_index','bad_correlation','bad_snapshot','changed','duplicate','no_remote','report','timeout','slow_guard','slow_count','slow_issue','pause_lost_issue','slow_snapshot','slow_report','pause_lost_report','duplicate_final'):
   with self.subTest(mode=mode):subprocess.run(['luajit','tests/authority_sector_create_driver.lua',mode],cwd=ROOT,check=True,capture_output=True)

if __name__=='__main__':unittest.main()
