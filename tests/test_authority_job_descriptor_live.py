"""Offline overlay, log and synthetic ownership tests; never runs X4."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_job_descriptor_live as live
import test_authority_job_attach_live as prior

class DescriptorHarnessTests(unittest.TestCase):
 def setUp(self):
  x=prior.AttachTests();x.setUp();self.base=x;self.ticket=x.ticket
 def test_synthetic_single_owner_async_and_faults(self):
  for mode in ('ok','disabled','timeout','bad_response','queue_fault'):
   with self.subTest(mode=mode):
    subprocess.run(['luajit','tests/authority_job_descriptor_attach.lua',mode],cwd=ROOT,
                   check=True,capture_output=True,text=True,timeout=5)
 def test_private_overlay_has_one_update_owner_and_protects_extras(self):
  with tempfile.TemporaryDirectory() as t:
   case=Path(t)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
   protected=live.install(case,profile,self.ticket,1,60)
   self.assertIn(md/'authority_job_descriptor_probe.xml',protected)
   self.assertIn(ui/'authority_job_descriptor_probe.lua',protected)
   self.assertEqual((ui/'authority_download_load_probe.lua').read_text().count("SetScript('onUpdate'"),1)
   self.assertNotIn("SetScript('onUpdate'",(ui/'authority_job_attach.lua').read_text())
   self.assertIn('authority_job_descriptor=true',(ui/'config.lua').read_text())
   manifest=(lab/'ui.xml').read_text()
   self.assertLess(manifest.index('authority_registry_resolve_string.lua'),manifest.index('authority_job_descriptor_probe.lua'))
   self.assertLess(manifest.index('authority_job_descriptor_probe.lua'),manifest.index('authority_job_attach.lua'))
 def rows(self):
  rows=self.base.rows();tag=live.TAG
  sample=(tag+'SAMPLE request='+self.ticket['world_epoch']+' epoch='+live.attach.archive.REGISTRY_EPOCH+
      ' sequence=2 index=10055 macro=ship_a owner=argon sector_macro=sector_a x=1 y=-2 z=3'
      ' game_before_request=10 game_before_pose=11 game_after_pose=12')
  return rows[:7]+[sample]+rows[7:]
 def test_descriptor_is_correlated_bounded_and_ordered(self):
  rows=self.rows();raw=lambda r:('\n'.join(r)+'\n').encode()
  result=live.validate(raw(rows),self.ticket,1)
  self.assertTrue(result['descriptor_sampled']);self.assertEqual(result['descriptor_index'],10055)
  self.assertFalse(result['descriptor_atomic']);self.assertFalse(result['birth_confirmed'])
  self.assertFalse(result['delivery_confirmed']);self.assertFalse(result['sector_identity_proven'])
  for bad in (rows[:7]+rows[8:], rows+[rows[7]], rows[:7]+[rows[7].replace('index=10055','index=10056')]+rows[8:],
              rows[:7]+[rows[7].replace('game_before_pose=11','game_before_pose=9')]+rows[8:],
              rows[:7]+[rows[7].replace('x=1','x=nan')]+rows[8:],
              rows[:6]+[rows[7]]+[rows[6]]+rows[8:]):
   with self.subTest(bad=bad),self.assertRaises(ValueError):live.validate(raw(bad),self.ticket,1)
 def test_partial_result_does_not_claim_sample(self):
  rows=self.rows();raw=lambda r:('\n'.join(r)+'\n').encode()
  self.assertIsNone(live.validate(raw(rows[:8]),self.ticket,1,partial=True))

if __name__=='__main__':unittest.main()
