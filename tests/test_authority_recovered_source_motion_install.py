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

 def test_real_time_motion_opt_in_and_invalid_combinations(self):
  cfg=self.ui/'config.lua';before=cfg.read_bytes()
  for value in (None, 1, 'true'):
   self.settings['real_time_motion']=value
   with self.assertRaises(ValueError):self.install()
   self.assertEqual(before,cfg.read_bytes())
  self.settings['real_time_motion']=True
  for option,value in (('selection',{'nonce':'6'*32,'candidates':(1,)}),
                       ('local_pair',{'nonce':'6'*32,'index':1})):
   self.settings[option]=value
   with self.assertRaises(ValueError):self.install()
   self.assertEqual(before,cfg.read_bytes())
   del self.settings[option]
  self.install()
  self.assertIn('authority_motion_real_time=true',cfg.read_text())
  owner=(self.ui/'authority_world_bridge_probe.lua').read_text()
  self.assertIn('real_time_motion=cfg.authority_motion_real_time',owner)
  subprocess.run(['luajit','-b',str(self.ui/'authority_world_bridge_probe.lua'),'/dev/null'],check=True,capture_output=True)

 def test_candidate_overlay_is_explicit_and_preserves_existing_md(self):
  before={p:p.read_bytes() for p in self.md.iterdir()}
  self.settings['selection']={'nonce':'6'*32,'candidates':(1,2)}
  result=self.install()
  for p,data in before.items():self.assertEqual(p.read_bytes(),data)
  script=self.md/'authority_registry_motion_candidate.xml';module=self.ui/'authority_registry_motion_candidate.lua'
  self.assertIn(script,result);self.assertIn(module,result);ET.parse(script)
  config=(self.ui/'config.lua').read_text();owner=(self.ui/'authority_world_bridge_probe.lua').read_text()
  self.assertIn('authority_motion_candidate_indices={1,2}',config)
  self.assertIn('selection={nonce=cfg.authority_motion_candidate_nonce',owner)
  for path in (module,self.ui/'authority_world_bridge_probe.lua'):
   subprocess.run(['luajit','-b',str(path),'/dev/null'],check=True,capture_output=True)

 def test_bad_candidate_context_is_rejected_before_mutation(self):
  cfg=self.ui/'config.lua';before=cfg.read_bytes()
  for selection in (None,{'nonce':'6'*32,'candidates':()}, {'nonce':'4'*32,'candidates':(1,)},
                    {'nonce':'6'*32,'candidates':(1,1)}, {'nonce':'6'*32,'candidates':(3,)},
                    {'nonce':'6'*32,'candidates':(True,)}):
   with self.subTest(selection=selection):
    self.settings['selection']=selection
    with self.assertRaises(ValueError):self.install()
    self.assertEqual(before,cfg.read_bytes())

 def test_local_pair_is_explicit_and_additive(self):
  self.settings['local_pair']={'nonce':'6'*32,'index':1}
  protected=self.install()
  pair=self.ui/'source_motion_local_pair.lua'
  config=(self.ui/'config.lua').read_text()
  owner=(self.ui/'authority_world_bridge_probe.lua').read_text()
  manifest=(self.lab/'ui.xml').read_text()
  self.assertIn(pair,protected)
  self.assertLess(manifest.index('ui/source_motion_local_pair.lua'),
                  manifest.index('ui/authority_recovered_source_motion.lua'))
  self.assertIn('authority_motion_pair_nonce="'+'6'*32+'"',config)
  self.assertIn('authority_motion_pair_index=1',config)
  self.assertIn('local_pair={nonce=cfg.authority_motion_pair_nonce,index=cfg.authority_motion_pair_index}',owner)
  for path in (pair,self.ui/'authority_world_bridge_probe.lua'):
   subprocess.run(['luajit','-b',str(path),'/dev/null'],check=True,capture_output=True)

 def test_bad_local_pair_rejected_before_mutation(self):
  config=self.ui/'config.lua';manifest=self.lab/'ui.xml';owner=self.ui/'authority_world_bridge_probe.lua'
  before=[p.read_bytes() for p in (config,manifest,owner)]
  for pair in (None,{'nonce':'6'*32,'index':True},{'nonce':'6'*32,'index':3},
               {'nonce':'4'*32,'index':1},{'nonce':'4'*16+'6'*16,'index':1}):
   with self.subTest(pair=pair):
    self.settings['local_pair']=pair
    with self.assertRaises(ValueError):self.install()
    self.assertEqual(before,[p.read_bytes() for p in (config,manifest,owner)])
  self.settings['local_pair']={'nonce':'6'*32,'index':1}
  self.settings['selection']={'nonce':'7'*32,'candidates':(1,)}
  with self.assertRaises(ValueError):self.install()
  self.assertEqual(before,[p.read_bytes() for p in (config,manifest,owner)])

 def test_pair_delivery_requires_explicit_true_and_adds_owner_option(self):
  self.settings['local_pair']={'nonce':'6'*32,'index':1,'delivery':True}
  self.install()
  owner=(self.ui/'authority_world_bridge_probe.lua').read_text()
  self.assertIn('index=cfg.authority_motion_pair_index,delivery=true',owner)
  subprocess.run(['luajit','-b',str(self.ui/'authority_world_bridge_probe.lua'),'/dev/null'],
                 check=True,capture_output=True)

 def test_pair_delivery_rejects_ambiguous_opt_in(self):
  config=self.ui/'config.lua';before=config.read_bytes()
  for value in (False,1,None,'true'):
   with self.subTest(value=value):
    self.settings['local_pair']={'nonce':'6'*32,'index':1,'delivery':value}
    with self.assertRaises(ValueError):self.install()
    self.assertEqual(before,config.read_bytes())

if __name__=='__main__':unittest.main()
