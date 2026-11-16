"""Offline checks for disposable sector-create process harness."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sector_create_live',ROOT/'tools/dev/authority_sector_create_live.py')
create=importlib.util.module_from_spec(spec);spec.loader.exec_module(create)

class SectorCreateLiveTests(unittest.TestCase):
 def setUp(self):
  self.ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,checkpoint_id=create.base.archive.CHECKPOINT_ID,sha256=create.base.archive.SHA256,attempt_id='b'*32,slot='save_009')
 def test_controller_guards(self):
  for mode in ('disabled','ok','late','pause_loss','time_change','timeout'):
   with self.subTest(mode=mode):subprocess.run(['luajit','tests/authority_sector_create_run.lua',mode],cwd=ROOT,check=True,capture_output=True)
 def test_install_single_owner_and_protected_variant(self):
  with tempfile.TemporaryDirectory() as t:
   case=Path(t)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
   protected=create.install(case,profile,self.ticket,2,'c'*32,['sector_a','sector_b'])
   loader=(ui/'authority_download_load_probe.lua').read_text();self.assertEqual(loader.count("SetScript('onUpdate'"),1)
   self.assertIn('X4LAN_SECTOR_CREATE_RUN_TICK()',loader)
   receiver=md/'authority_ship_create_receiver.xml'
   self.assertEqual(receiver.read_bytes(),(ROOT/'tools/dev/authority_sector_create_receiver.xml').read_bytes())
   self.assertIn(receiver,protected);self.assertIn(ui/'authority_sector_create_owner.lua',protected)
   self.assertIn('AUTH_SECTOR_CREATE ERROR owner',(ui/'authority_sector_create_owner.lua').read_text())
   self.assertNotIn('authority_job_ship_events.xml',{p.name for p in md.iterdir()})
 def test_rows_and_terminal_fence(self):
  old=create._base_check;create._base_check=lambda *a,**kw:{'reported_game_time':3.0}
  try:
   tag=create.TAG;rows=[]
   for i,(idx,stage) in enumerate(((3,'create'),(3,'replay'),(4,'create'),(4,'replay'),(3,'final'),(4,'final'))):
    rows.append(f'{tag}ROW index={idx} stage={stage} macro=sector_{"a" if idx==3 else "b"} location={"remote" if idx==3 else "local"} x=-400 y=100000 z=500 count={11 if i<2 else 12} game=3')
   rows.extend((tag+'PENDING',tag+'DONE game=3'))
   prefix=create.base.load.TAG.decode()+'pause_observed|ticket'
   raw=lambda x:('\n'.join([prefix]+x)+'\n').encode()
   result=create.validate(raw(rows),self.ticket,2,['sector_a','sector_b'])
   self.assertEqual(len(result['created_records']),6);self.assertTrue(result['at_least_one_remote_sector'])
   for i in range(8):self.assertIsNone(create.validate(raw(rows[:i]),self.ticket,2,['sector_a','sector_b'],partial=True))
   bad=[rows+[tag+'ERROR owner'],rows+[rows[-1]],rows[:2]+[rows[2].replace('count=12','count=13')]+rows[3:],
        rows[:4]+[rows[4].replace('location=remote','location=local')]+rows[5:],
        [row.replace('location=remote','location=local') for row in rows],rows[:6]+[tag+'DONE game=3',rows[6]]]
   for value in bad:
    with self.subTest(rows=value):
     with self.assertRaises(ValueError):create.validate(raw(value),self.ticket,2,['sector_a','sector_b'])
   with self.assertRaises(ValueError):create.validate(('\n'.join(rows+[prefix])+'\n').encode(),self.ticket,2,['sector_a','sector_b'])
  finally:create._base_check=old
 def test_final_source_check_invalidates_changed_archive(self):
  with patch.object(create.base.archive,'_path_fingerprints',return_value={'changed':1}):
   result={'success':True}
   with self.assertRaisesRegex(ValueError,'source archive changed'):create.finalize_result(result,Path('/archive'),{'old':1})
   self.assertFalse(result['collision_free_proven']);self.assertIn('two-sector',result['scope'])
  with patch.object(create.base.archive,'_path_fingerprints',side_effect=AssertionError('no source read on failure')):
   result={'success':False};create.finalize_result(result,Path('/archive'),{})
   self.assertFalse(result['success'])
 def test_fault_logs_include_late_owner_error(self):
  self.assertTrue(create.fault_log(b'[X4LAN] AUTH_SECTOR_CREATE ERROR owner\n'))
  self.assertTrue(create.fault_log(b'Invalid data types for arithmetic operation!\n'))
  self.assertFalse(create.fault_log(b'[X4LAN] AUTH_SECTOR_CREATE PENDING\n'))

if __name__=='__main__':unittest.main()
