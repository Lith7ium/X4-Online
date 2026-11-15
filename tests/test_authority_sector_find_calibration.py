"""Offline checks for the opt-in, isolated sector-find calibration."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sector_find',ROOT/'tools/dev/authority_sector_find_calibration_live.py')
find=importlib.util.module_from_spec(spec);spec.loader.exec_module(find)

class SectorFindTests(unittest.TestCase):
 def test_state_machine(self):
  for mode in ('ok','disabled','dispatch','wrong_id','wrong_epoch','wrong_macro','wrong_find','pause_loss','duplicate','timeout','refused','invalid'):
   with self.subTest(mode=mode): subprocess.run(['luajit','tests/authority_sector_find_calibration.lua',mode],cwd=ROOT,check=True,capture_output=True)
 def test_md_is_bounded_and_read_only(self):
  root=ET.parse(ROOT/'tools/dev/authority_sector_find_calibration.xml').getroot()
  search=root.find('.//find_sector');self.assertEqual(search.get('multiple'),'true');self.assertEqual(search.get('macro'),'macro.{$v.$macro}')
  conditions=[x.get('value','') for x in root.findall('.//do_if')]
  self.assertTrue(any('$matches.count == 1' in x and '$matches.{1} == $sector' in x for x in conditions))
  self.assertFalse(root.findall('.//create_ship'));self.assertFalse(root.findall('.//set_object_velocity'))
  result=root.find('.//raise_lua_event[@name="\'X4AuthoritySectorFindCalibration.Result\'"]')
  for value in ('$v.$request_id','$v.$epoch','$index','$ship','$sector','$matches.{1}','$v.$macro'):self.assertIn(value,result.get('param'))
 def test_install_one_owner(self):
  with tempfile.TemporaryDirectory() as t:
   case=Path(t)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
   ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,checkpoint_id=find.base.archive.CHECKPOINT_ID,sha256=find.base.archive.SHA256,attempt_id='b'*32,slot='save_009')
   protected=find.install(case,profile,ticket,2,'c'*32,['sector_1','sector_2'])
   owner=(ui/'authority_download_load_probe.lua').read_text();self.assertEqual(owner.count("SetScript('onUpdate'"),1)
   self.assertIn('X4LAN_SECTOR_FIND_CALIBRATION_READY()',owner)
   self.assertIn(md/'authority_sector_find_calibration.xml',protected);self.assertIn(ui/'authority_sector_find_calibration.lua',protected)
   for macros in (['sector_1','sector_1'],['sector_1','bad"'],['sector_1','null']):
    with self.assertRaises(ValueError):find.install(case,profile,ticket,2,'c'*32,macros)
 def test_evidence_refuses_inconsistency(self):
  old=find._base_check;find._base_check=lambda *a,**k:{'reported_game_time':3}
  try:
   rows=[find.TAG+'ROW slot=1 sector_macro=sector_1 game=3',find.TAG+'ROW slot=2 sector_macro=sector_2 game=3',find.TAG+'DONE samples=2 game=3']
   raw=lambda r:('\n'.join([find.base.load.TAG.decode()+'pause_observed|ticket']+r)+'\n').encode()
   self.assertTrue(find.validate(raw(rows),{},2,['sector_1','sector_2'])['exactly_one_match_each'])
   self.assertIsNone(find.validate(raw(rows[:2]),{},2,['sector_1','sector_2'],partial=True))
   with self.assertRaises(ValueError):find.validate(('\n'.join(rows+[find.base.load.TAG.decode()+'pause_observed|ticket'])+'\n').encode(),{},2,['sector_1','sector_2'])
   for bad in (rows+[rows[-1]],[rows[1],rows[0],rows[2]],[rows[0],rows[1].replace('sector_2','sector_3'),rows[2]],[rows[0],rows[1],rows[2].replace('game=3','game=4')]):
    with self.assertRaises(ValueError):find.validate(raw(bad),{},2,['sector_1','sector_2'])
  finally:find._base_check=old

if __name__=='__main__':unittest.main()
