"""Offline checks for isolated multi-sector reader; never starts X4."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('multi',ROOT/'tools/dev/authority_multi_sector_read_live.py')
multi=importlib.util.module_from_spec(spec);spec.loader.exec_module(multi)

class MultiSectorTests(unittest.TestCase):
 def test_state_machine_and_failures(self):
  for mode in ('ok','disabled','dispatch','wrong_id','wrong_epoch','actor_change','sector_change','initial_mismatch','bad_hex','pause_loss','duplicate','timeout'):
   with self.subTest(mode=mode):
    subprocess.run(['luajit','tests/authority_multi_sector_read.lua',mode],cwd=ROOT,check=True,capture_output=True)
 def test_xml_is_read_only_and_correlated(self):
  root=ET.parse(ROOT/'tools/dev/authority_multi_sector_read.xml').getroot()
  self.assertFalse(root.findall('.//set_object_velocity'));self.assertFalse(root.findall('.//create_ship'))
  event=root.find('.//raise_lua_event[@name="\'X4AuthorityMultiSectorRead.Result\'"]')
  for v in ('$request_id','$epoch','$index','$ship','$sector'): self.assertIn(v,event.get('param'))
 def test_install_uses_one_owner_and_protects_files(self):
  with tempfile.TemporaryDirectory() as t:
   case=Path(t)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'): p.write_text('test')
   ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,checkpoint_id=multi.base.archive.CHECKPOINT_ID,sha256=multi.base.archive.SHA256,attempt_id='b'*32,slot='save_009')
   protected=multi.install(case,profile,ticket,2,'c'*32)
   owner=(ui/'authority_download_load_probe.lua').read_text()
   self.assertEqual(owner.count("SetScript('onUpdate'"),1)
   self.assertIn("if state=='done' then X4LAN_MULTI_SECTOR_READY();return end",owner)
   self.assertIn(md/'authority_multi_sector_read.xml',protected);self.assertIn(ui/'authority_multi_sector_read.lua',protected)
 def test_evidence_validation(self):
  prior=multi.base_check;multi.base_check=lambda *a,**kw: {}
  try:
   rows=['[X4LAN] AUTH_MULTI_SECTOR SAMPLE slot=%d n=%d real_before=%d real_after=%s game_before=%d game_after=%s x=1 y=2 z=3'%(i%2+1,i//2+1,i+1,i+1.1,i+4,i+4.1) for i in range(6)]
   rows+=['[X4LAN] AUTH_MULTI_SECTOR DONE samples=6 game=10']
   raw=lambda v: ('\n'.join(v)+'\n').encode()
   self.assertEqual(len(multi.validate(raw(rows),{},2)['samples']),6)
   self.assertIsNone(multi.validate(raw(rows[:-1]),{},2,partial=True))
   for bad in (rows+[rows[-1]],rows[:2]+[rows[2].replace('slot=1','slot=2')]+rows[3:],rows[:2]+[rows[2].replace('real_before=3','real_before=1')]+rows[3:]):
    with self.assertRaises(ValueError): multi.validate(raw(bad),{},2)
  finally: multi.base_check=prior

if __name__=='__main__': unittest.main()
