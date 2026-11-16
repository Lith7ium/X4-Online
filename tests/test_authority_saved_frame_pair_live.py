"""Offline installer/coordinator checks; never launches X4."""
from pathlib import Path
import sys,tempfile,time,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_saved_frame_pair_live as m
from tests.test_authority_saved_frame_compare import log

class SavedFramePair(unittest.TestCase):
 def ticket(self):
  return dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
   checkpoint_id=m.archive.CHECKPOINT_ID,sha256=m.archive.SHA256,attempt_id='b'*32,slot='save_009')
 def test_isolated_installer_uses_one_paused_owner_and_protects_probe(self):
  with tempfile.TemporaryDirectory() as tmp:
   case=Path(tmp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
             lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
   files=m.install(case,profile,self.ticket(),{'role':'server'},'f'*32,300,60)
   owner=(ui/'authority_download_load_probe.lua').read_text();self.assertEqual(owner.count("SetScript('onUpdate'"),1)
   self.assertIn('X4LAN_FRAME_READ_TICK()',owner);self.assertIn('if not engine.is_paused()',owner)
   self.assertIn('authority_frame_enabled=true',(ui/'config.lua').read_text())
   self.assertIn(md/'authority_frame_read.xml',files);self.assertIn(ui/'authority_frame_read.lua',files)
   self.assertEqual((md/'authority_ship_registry.xml').read_bytes(),m.archive.saved_state_script('authority_ship_registry.xml').read_bytes())
   self.assertNotIn('<create_ship',(md/'authority_frame_read.xml').read_text())
 def test_coordinator_requires_two_distinct_processes_and_matching_rows(self):
  c=m.FrameCoordinator({m.evidence.SECTOR:(1318,)})
  for role,nonce in (('server','a'*32),('client','b'*32)):
   c.add_role(role);c.roles[role].update(profile=Path('/'+role),nonce=nonce,ticket={})
   c.launches[role]=(role,1,Path('/game'))
  def capture(path,previous):
   role=path.parts[1];return (m.base.load.TAG+b'pause_observed|x\n'+log(nonce=c.roles[role]['nonce']),(role,1,b'x'))
  with patch.object(m.base,'read_live_log',side_effect=capture),patch.object(m.pair,'load_observation',return_value=True),\
       patch.object(m.base.load,'game_identity',side_effect=lambda p,*_: (1 if p=='server' else 2,123)):
   r=c.run({'deadline':time.monotonic()+30,'check':lambda:True});self.assertEqual(r['station_count'],3)
  c2=m.FrameCoordinator({m.evidence.SECTOR:(1318,)})
  for role in ('server','client'):
   c2.add_role(role);c2.launches[role]=(role,1,Path('/game'))
  with patch.object(m.base.load,'game_identity',return_value=(1,123)):
   with self.assertRaisesRegex(RuntimeError,'distinct'):c2.run({'deadline':time.monotonic()+30,'check':lambda:True})
 def test_existing_lifecycle_hooks_are_restored_on_exception(self):
  import argparse
  old=(m.pair.coordinator.CensusCoordinator,m.pair.installer.install,m.pair.load_observation,m.pair.owned.spawn_owned_gated)
  with patch.object(m.pair,'run',side_effect=RuntimeError('deliberate')):
   with self.assertRaises(RuntimeError):m.run(argparse.Namespace())
  self.assertEqual(old,(m.pair.coordinator.CensusCoordinator,m.pair.installer.install,m.pair.load_observation,m.pair.owned.spawn_owned_gated))
if __name__=='__main__':unittest.main()
