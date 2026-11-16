"""Opt-in motion install into one existing owner, no X4."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_participant_motion_install as m
class Install(unittest.TestCase):
 def test_one_owner_and_conflicting_context_rejected(self):
  settings=dict(participant_port=1234,participant_lease='a'*32,job_port=1235,lease='b'*32,attempt='c'*32,
      epoch=m.base.archive.REGISTRY_EPOCH,generation='d'*32,nonce='e'*32,seed=7183,timeout=20)
  motion=dict(port=1236,lease='1'*32,attempt='2'*32,epoch=settings['epoch'],generation=settings['generation'],nonce='4'*32,timeout=10,max_age=5,max_tracks=100)
  with tempfile.TemporaryDirectory() as tmp:
   case=Path(tmp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
   ticket=dict(world_epoch='f'*32,connection_handle=1,baseline_id=1,load_generation=1,checkpoint_id=m.base.archive.CHECKPOINT_ID,
       sha256=m.base.archive.SHA256,attempt_id='0'*32,slot='save_009')
   with self.assertRaises(ValueError):m.install(case,profile,ticket,settings,{'cluster_01_sector001_macro':41},dict(motion,port=1235))
   with self.assertRaises(ValueError):m.install(case,profile,ticket,settings,{'cluster_01_sector001_macro':41},dict(motion,generation='3'*32))
   files=m.install(case,profile,ticket,settings,{'cluster_01_sector001_macro':41},motion)
   self.assertIn(md/'authority_replica_motion_bind.xml',files)
   self.assertIn(ui/'motion_client_owner.lua',files)
   self.assertEqual((ui/'authority_download_load_probe.lua').read_text().count("SetScript('onUpdate'"),1)
   self.assertIn('authority_motion_client_enabled=true',(ui/'config.lua').read_text())
   session=(ui/'authority_participant_job_session.lua').read_text()
   self.assertIn('motion:tick()',session);self.assertNotIn('SetScript(',session)
if __name__=='__main__':unittest.main()
