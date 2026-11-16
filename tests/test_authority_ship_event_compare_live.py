"""Offline owner, installer and result-validation checks; never starts X4."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_ship_event_compare_live as m
class CompareLive(unittest.TestCase):
 def ticket(self):
  return dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
              checkpoint_id=m.archive.CHECKPOINT_ID,sha256=m.archive.SHA256,attempt_id='b'*32,slot='save_009')
 def test_real_owner_and_fake_md_ffi(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC',str(ROOT/'tests/fixtures/ship_event_compare_run_fake_abi.c'),'-o',str(lib)],check=True,capture_output=True)
   subprocess.run(['luajit','tests/authority_ship_event_compare_run.lua'],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib)),check=True,capture_output=True,timeout=5)
 def test_private_installer(self):
  with tempfile.TemporaryDirectory() as tmp:
   case=Path(tmp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
   files=m.install(case,profile,self.ticket(),1,60,'c'*32)
   self.assertIn('authority_ship_event_compare_run=true',(ui/'config.lua').read_text())
   self.assertIn(md/'authority_ship_event_compare.xml',files)
   self.assertEqual((ui/'authority_download_load_probe.lua').read_text().count("SetScript('onUpdate'"),1)
   self.assertEqual((md/'authority_ship_registry.xml').read_bytes(),m.archive.saved_state_script('authority_ship_registry.xml').read_bytes())
 def test_log_validation_and_inconclusive(self):
  t=self.ticket();fields='|'.join(str(t[k]) for k in m.base.load.FIELDS);load=m.base.load.TAG.decode()
  prefix=[load+'load_requested|'+fields,'[X4LAN] AUTH_MARKER load INSPECTED '+m.archive.MARKER,load+'pause_observed|'+fields]
  encode=lambda rows: ('\n'.join(prefix+[m.TAG+x for x in rows])+'\n').encode()
  empty=m.validate(encode(['READY','RUNNING','DONE 0']),t,1);self.assertEqual(empty['classification'],'inconclusive_no_events')
  result=m.validate(encode(['READY','RUNNING','ROW 1 activation 41 9007199254740993','DONE 1']),t,1)
  self.assertEqual(result['events'][0]['local_actor'],'9007199254740993');self.assertFalse(result['birth_confirmed'])
  self.assertIsNone(m.validate(encode(['READY','RUNNING']),t,1,partial=True))
  for rows in (['RUNNING','READY','DONE 0'],['ROW 1 god 0 42','READY','RUNNING','DONE 1'],['READY','RUNNING','ROW 2 god 0 42','DONE 1'],['READY','RUNNING','DONE 0','DONE 0'],['READY','RUNNING','ROW 1 god 0 18446744073709551616','DONE 1']):
   with self.assertRaises(ValueError):m.validate(encode(rows),t,1)
