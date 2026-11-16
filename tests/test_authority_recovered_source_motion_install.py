"""Private overlay and source composition tests; no X4 start."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_recovery_bridge_live as recovery
import authority_recovery_registry_status as status
import authority_recovery_registry_witness as witness
import authority_recovered_source_motion_install as subject

@unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
class RecoveredMotionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.case=Path(self.temp.name)/'case';self.profile=self.case/'home/.config/EgoSoft/X4/45841'
  (self.profile/'save').mkdir(parents=True);(self.profile/'content.xml').write_text('');(self.profile/'config.xml').write_text('')
  self.lab=self.case/'extensions/x4_lan_lab';self.ui=self.lab/'ui';self.md=self.lab/'md'
  def fake_base(case,port,lease,epoch,marker_required):
   self.ui.mkdir(parents=True);self.md.mkdir();(self.lab/'native').mkdir()
   (self.ui/'authority_world_bridge_probe.lua').write_text((ROOT/'tools/dev/authority_world_bridge_probe.lua').read_text())
  with patch.object(recovery.bridge_install,'install_probe',side_effect=fake_base):
   recovery.install_probe(self.case,self.profile,1234,'a'*32,'b'*32)
  status.install(self.case,'a'*32,('ready','c'*32,2,'d'*64))
  witness.install(self.case,'e'*32,'c'*32,2,'verify',allow_resume=True)
  self.status=('ready','c'*32,2,'d'*64)
  self.settings={'port':2345,'lease':'1'*32,'attempt':'2'*32,'generation':'3'*32,
                 'nonce':'4'*32,'saved_nonce':'5'*32,'timeout':5}
 def install(self):return subject.install(self.case,self.profile,self.status,self.settings)
 def test_additive_overlay_preserves_existing_md_and_compiles(self):
  before={p:p.read_bytes() for p in self.md.iterdir()}
  owner_before=(self.ui/'authority_world_bridge_probe.lua').read_text()
  result=self.install()
  for p,data in before.items():self.assertEqual(p.read_bytes(),data)
  self.assertEqual(set(self.md.iterdir()),set(before)|{self.md/'authority_job_descriptor_probe.xml'})
  for p in result:self.assertTrue(p.is_file())
  self.assertEqual(len(result),len(set(result)))
  ET.parse(self.md/'authority_job_descriptor_probe.xml')
  owner=(self.ui/'authority_world_bridge_probe.lua').read_text()
  self.assertEqual(owner.count("SetScript('onUpdate'"),1)
  self.assertEqual(owner.count('local activated=false'),1)
  self.assertIn('authority_motion_epoch="'+self.status[1]+'"',(self.ui/'config.lua').read_text())
  self.assertIn('authority_motion_baseline=2',(self.ui/'config.lua').read_text())
  self.assertIn('local registry_witness=nil',owner)
  self.assertIn(" local ok,reason=bridge:update();assert(ok,reason)\n",owner_before)
  for path in [self.ui/'authority_world_bridge_probe.lua',*(self.ui/name for _,name in subject.MODULES)]:
   subprocess.run(['luajit','-b',str(path),'/dev/null'],check=True,capture_output=True)
  with self.assertRaises(ValueError):self.install()
 def test_reject_bad_context_or_overwrite_before_mutation(self):
  cfg=self.ui/'config.lua';manifest=self.lab/'ui.xml';probe=self.ui/'authority_world_bridge_probe.lua'
  before=[p.read_bytes() for p in (cfg,manifest,probe)]
  for key,value in (('port',1234),('timeout',float('nan')),('lease','a'*32),('saved_nonce','4'*32)):
   with self.subTest(key=key):
    old=self.settings[key];self.settings[key]=value
    with self.assertRaises(ValueError):self.install()
    self.settings[key]=old;self.assertEqual(before,[p.read_bytes() for p in (cfg,manifest,probe)])
  for invalid in (('ready','f'*32,2,'d'*64),('ready','c'*32,1,'d'*64)):
   with self.subTest(status=invalid):
    with self.assertRaisesRegex(ValueError,'differs from recovery owner'):
     subject.install(self.case,self.profile,invalid,self.settings)
    self.assertEqual(before,[p.read_bytes() for p in (cfg,manifest,probe)])
  config_text=cfg.read_text();bad_text=config_text.replace('authority_load_save_path=', 'authority_load_save_path="wrong",unused_path=')
  cfg.write_text(bad_text);bad_snapshot=[p.read_bytes() for p in (cfg,manifest,probe)]
  with self.assertRaisesRegex(ValueError,'save path differs'):self.install()
  self.assertEqual(bad_snapshot,[p.read_bytes() for p in (cfg,manifest,probe)])
  cfg.write_text(config_text)
  (self.md/'authority_job_descriptor_probe.xml').write_text('existing')
  with self.assertRaises(ValueError):self.install()
  self.assertEqual((self.md/'authority_job_descriptor_probe.xml').read_text(),'existing')
  self.assertEqual(before,[p.read_bytes() for p in (cfg,manifest,probe)])
 def test_real_lua_modules_compose_with_simulated_x4(self):
  subprocess.run(['luajit','tests/authority_recovered_source_motion.lua'],cwd=ROOT,check=True,capture_output=True,timeout=5)

if __name__=='__main__':unittest.main()
