"""Private source installer and shared update owner; no X4 is started."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_source_single_job_install as m
class Install(unittest.TestCase):
 def ticket(self):
  return dict(world_epoch='f'*32,connection_handle=1,baseline_id=1,load_generation=1,
              checkpoint_id=m.archive.CHECKPOINT_ID,sha256=m.archive.SHA256,attempt_id='0'*32,slot='save_009')
 def settings(self):
  return dict(control_port=1234,control_lease='a'*32,job_port=1235,lease='b'*32,attempt='c'*32,
              epoch=m.archive.REGISTRY_EPOCH,generation='d'*32,descriptor_request='e'*32,
              timeout=110,host_timeout=10,window=60,capacity=128,baseline=m.archive.COUNT)
 def test_source_overlay_single_update_and_exact_saved_registry(self):
  with tempfile.TemporaryDirectory() as tmp:
   case=Path(tmp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
   with self.assertRaises(ValueError):m.install(case,profile,self.ticket(),{**self.settings(),'job_port':1234})
   with self.assertRaises(ValueError):m.install(case,profile,self.ticket(),{**self.settings(),'descriptor_request':'a'*32})
   with self.assertRaises(ValueError):m.install(case,profile,self.ticket(),{**self.settings(),'max_events':9})
   files=m.install(case,profile,self.ticket(),self.settings())
   owner=(ui/'authority_download_load_probe.lua').read_text()
   self.assertEqual(owner.count("SetScript('onUpdate'"),1);self.assertIn('X4LAN_SOURCE_SINGLE_JOB_TICK()',owner)
   self.assertNotIn('SetScript(', (ui/'authority_source_single_job_session.lua').read_text())
   self.assertIn(ui/'source_single_job_owner.lua',files);self.assertIn(lab/'native/x4lan_net.so',files)
   self.assertEqual((md/'authority_ship_registry.xml').read_bytes(),m.archive.saved_state_script('authority_ship_registry.xml').read_bytes())
   self.assertEqual({p.name for p in md.iterdir()},set(m.MD))
 def test_source_control_and_job_tick_are_serialized(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'fake.so'
   subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_running_owner_abi.c'),'-o',str(lib)],check=True,capture_output=True)
   subprocess.run(['luajit','tests/authority_source_single_job_session.lua'],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib)),check=True,capture_output=True,text=True,timeout=5)
