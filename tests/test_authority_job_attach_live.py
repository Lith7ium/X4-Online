"""Offline tests for the isolated saved-registry attach diagnostic."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('job_attach',ROOT/'tools/dev/authority_job_attach_live.py')
attach=importlib.util.module_from_spec(spec);spec.loader.exec_module(attach)

class AttachTests(unittest.TestCase):
 def setUp(self):
  self.ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
   checkpoint_id=attach.archive.CHECKPOINT_ID,sha256=attach.archive.SHA256,attempt_id='b'*32,slot='save_009')
 def test_owner_state_machine(self):
  for mode in ('ok','disabled','fault','bad_path','pause_loss'):
   with self.subTest(mode=mode): subprocess.run(['luajit','tests/authority_job_attach.lua',mode],cwd=ROOT,check=True,capture_output=True)
 def test_overlay_single_owner_and_saved_scripts(self):
  with tempfile.TemporaryDirectory() as t:
   case=Path(t)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'): p.write_text('test')
   protected=attach.install(case,profile,self.ticket,1,60)
   self.assertEqual({p.name for p in md.iterdir()},set(attach.MD))
   owner=(ui/'authority_download_load_probe.lua').read_text()
   self.assertEqual(owner.count("SetScript('onUpdate'"),1)
   self.assertIn('X4LAN_AUTHORITY_MARKER_READY()',owner);self.assertIn('X4LAN_JOB_ATTACH_UPDATE()',owner)
   scripts=''.join((ui/n).read_text() for n in attach.UI)
   self.assertNotIn("SetScript('onUpdate'",scripts)
   self.assertEqual((md/'authority_ship_registry.xml').read_bytes(),(ROOT/'tools/dev/authority_ship_registry.xml').read_bytes())
   self.assertIn(md/'authority_job_ship_events.xml',protected)
 def rows(self):
  t=self.ticket;load=attach.base.load.TAG.decode();f='|'.join(str(t[k]) for k in attach.base.load.FIELDS);e=attach.archive.REGISTRY_EPOCH;r=t['world_epoch'];tag=attach.TAG
  return [load+'load_requested|'+f,'[X4LAN] AUTH_MARKER load INSPECTED '+attach.archive.MARKER,
   load+'pause_observed|'+f,tag+'READY registry_epoch='+e+' run_epoch='+r+' baseline=10054',tag+'RESUMED run_epoch='+r,
   tag+'EVENT sequence=1 index=17 class=previously_unobserved_existing_index',
   tag+'EVENT sequence=2 index=10055 class=new_registry_entry',tag+'EVENT sequence=3 index=17 class=previously_observed',
   tag+'SUMMARY observed=3 acknowledged=3 baseline=10054 class=local_activations_observed',tag+'PAUSED run_epoch='+r]
 def test_evidence_fails_closed(self):
  rows=self.rows();raw=lambda r: ('\n'.join(r)+'\n').encode()
  self.assertEqual(attach.validate(raw(rows),self.ticket,1)['observed'],3)
  for i in range(len(rows)): self.assertIsNone(attach.validate(raw(rows[:i]),self.ticket,1,partial=True))
  mutations=[rows[:3]+[rows[4],rows[3]]+rows[5:],rows+[rows[-1]],
   rows[:5]+[rows[5].replace('sequence=1','sequence=2')]+rows[6:],
   rows[:6]+[rows[6].replace('index=10055','index=10056')]+rows[7:],
   rows[:7]+[rows[7].replace('index=17','index=18')]+rows[8:],
   rows[:8]+[rows[8].replace('acknowledged=3','acknowledged=2')]+rows[9:]]
  for bad in mutations:
   with self.subTest(bad=bad):
    with self.assertRaises(ValueError): attach.validate(raw(bad),self.ticket,1)
 def test_zero_events_inconclusive(self):
  rows=self.rows();rows=rows[:5]+[attach.TAG+'SUMMARY observed=0 acknowledged=0 baseline=10054 class=inconclusive_no_events',rows[-1]]
  result=attach.validate(('\n'.join(rows)+'\n').encode(),self.ticket,1)
  self.assertFalse(result['event_observed']);self.assertEqual(result['classification'],'inconclusive_no_events')
 def test_entire_private_save_directory_is_read_only(self):
  previous=attach._readonly_save_command
  attach._readonly_save_command=lambda *args: ['bwrap','--ro-bind','file','file','--die-with-parent']
  try:
   cmd=attach.readonly_save_command(None,None,None,None,None,None,None,None,Path('/private/45841/save/save_009.xml.gz'))
   self.assertEqual(cmd[-4:],['--ro-bind','/private/45841/save','/private/45841/save','--die-with-parent'])
   with self.assertRaises(ValueError): attach.readonly_save_command(None,None,None,None,None,None,None,None,Path('/other/save_009.xml.gz'))
  finally: attach._readonly_save_command=previous
 def test_source_disjoint(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);store=root/'archive'/'checkpoints';store.mkdir(parents=True)
   for out in (root,root/'archive'/'new',store/'new'):
    with self.assertRaises(ValueError): attach.census.ensure_separate(out,store)
   attach.census.ensure_separate(root/'other',store)

if __name__=='__main__': unittest.main()
