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
  old=(m.pair.coordinator.CensusCoordinator,m.pair.installer.install,m.pair.load_observation,m.pair.owned.spawn_owned_gated,m.pair.verify_saved_overlay)
  with patch.object(m.pair,'run',side_effect=RuntimeError('deliberate')):
   with self.assertRaises(RuntimeError):m.run(argparse.Namespace(diagnostic_current_registry_script=True,
    expected_current_registry_sha256=m.base.stable_read(m.CURRENT_REGISTRY,1<<20,collect=False)[1]))
  self.assertEqual(old,(m.pair.coordinator.CensusCoordinator,m.pair.installer.install,m.pair.load_observation,m.pair.owned.spawn_owned_gated,m.pair.verify_saved_overlay))
 def test_opt_in_installs_current_registry_into_private_overlay(self):
  with tempfile.TemporaryDirectory() as tmp:
   case=Path(tmp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
             lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
   files=m.install(case,profile,self.ticket(),{'role':'client'},'f'*32,300,60,current_registry=True)
   self.assertIn(md/m.REGISTRY_NAME,files)
   self.assertEqual((md/m.REGISTRY_NAME).read_bytes(),m.CURRENT_REGISTRY.read_bytes())
   for name in set(m.BASE_MD)-{m.REGISTRY_NAME}:
    self.assertEqual((md/name).read_bytes(),m.archive.saved_state_script(name).read_bytes())
 def test_current_registry_overlay_is_explicit_and_other_scripts_remain_pinned(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);store=root/'archive/checkpoints';store.mkdir(parents=True)
   archived=store.parent/'server/case/extensions/x4_lan_lab/md';archived.mkdir(parents=True)
   case=root/'case';md=case/'extensions/x4_lan_lab/md';md.mkdir(parents=True)
   for name in m.BASE_MD:
    raw=m.archive.saved_state_script(name).read_bytes()
    (archived/name).write_bytes(raw);(md/name).write_bytes(raw)
   digest=m.base.stable_read(m.CURRENT_REGISTRY,1<<20,collect=False)[1]
   coordinator=m.FrameCoordinator({m.evidence.SECTOR:(1318,)},current_registry=True,expected_registry_sha256=digest)
   with self.assertRaisesRegex(ValueError,'selected script'):coordinator.verify_overlay(case,store)
   (md/m.REGISTRY_NAME).write_bytes(m.CURRENT_REGISTRY.read_bytes())
   coordinator.verify_overlay(case,store)
   (md/'authority_identity_fixture.xml').write_bytes(b'wrong fixture')
   with self.assertRaisesRegex(ValueError,'selected script'):coordinator.verify_overlay(case,store)
 def test_current_registry_requires_expected_ship_on_both_sides(self):
  digest=m.base.stable_read(m.CURRENT_REGISTRY,1<<20,collect=False)[1]
  coordinator=m.FrameCoordinator({m.evidence.SECTOR:(1318,)},current_registry=True,expected_registry_sha256=digest)
  good=log().replace(b'ABC-123 ship_macro argon',b'WRG-830 ship_ter_m_corvette_01_a_macro pioneers')
  good=m.evidence.parse(good,'a'*32);bad=m.evidence.parse(log(),'a'*32)
  self.assertEqual(coordinator.compare(good,good)['ship_code'],'WRG-830')
  for left,right in ((good,bad),(bad,good)):
   with self.assertRaisesRegex(ValueError,'test ship identity'):coordinator.compare(left,right)
 def test_current_registry_source_change_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   script=Path(tmp)/'current.xml';script.write_bytes(b'first')
   with patch.object(m,'CURRENT_REGISTRY',script):
    digest=m.base.stable_read(script,1<<20,collect=False)[1]
    coordinator=m.FrameCoordinator({m.evidence.SECTOR:(1318,)},current_registry=True,expected_registry_sha256=digest)
    script.write_bytes(b'second')
    with self.assertRaisesRegex(ValueError,'changed'):coordinator.check_sources()
 def test_current_registry_diagnostic_requires_matching_explicit_digest(self):
  import argparse
  with patch.object(m.pair,'run') as pair_run:
   for digest in (None,'incorrect','a'*63):
    with self.subTest(digest=digest),self.assertRaisesRegex(ValueError,'SHA-256 required'):
     m.run(argparse.Namespace(diagnostic_current_registry_script=True,expected_current_registry_sha256=digest))
   pair_run.assert_not_called()
  with self.assertRaisesRegex(ValueError,'SHA-256 differs'):
   m.FrameCoordinator({m.evidence.SECTOR:(1318,)},current_registry=True,expected_registry_sha256='0'*64)
  with self.assertRaisesRegex(ValueError,'requires current registry diagnostic'):
   m.run(argparse.Namespace(diagnostic_current_registry_script=False,expected_current_registry_sha256='0'*64))
if __name__=='__main__':unittest.main()
