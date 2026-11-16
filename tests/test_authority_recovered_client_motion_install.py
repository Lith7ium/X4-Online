"""Disposable overlay and actual Lua composition; no X4 is started."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_load_live as load
import authority_recovered_client_motion_install as subject

class Install(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.case=Path(self.temp.name)/'case';self.profile=self.case/'home/.config/EgoSoft/X4/45841'
  (self.profile/'save').mkdir(parents=True)
  self.lab=self.case/'extensions/x4_lan_lab';self.ui=self.lab/'ui';self.md=self.lab/'md'
  self.ui.mkdir(parents=True);self.md.mkdir()
  self.status=('ready','c'*32,100,'d'*64)
  self.settings={'port':2345,'lease':'1'*32,'attempt':'2'*32,'generation':'3'*32,'nonce':'4'*32,'router_generation':'5'*32,'timeout':5,'index':42}
  cfg='X4LAN_CONFIG = {test_profile="45841",authority_download_load=true,authority_load_save_path='+load.lua_literal(str(self.profile/'save'))
  cfg+=',authority_ticket={world_epoch="'+'e'*32+'",attempt_id="'+'f'*32+'"},authority_participant_port=1234,authority_participant_lease="'+'a'*32+'"}\n'
  (self.ui/'config.lua').write_text(cfg)
  (self.lab/'ui.xml').write_text('<ui>\n    <file name="ui/authority_download_load_probe.lua" />\n    <file name="ui/authority_two_x4_participant_probe.lua" />\n</ui>\n')
  (self.ui/'authority_two_x4_participant_probe.lua').write_text((ROOT/'tools/dev/authority_two_x4_participant_probe.lua').read_text())
  code=(ROOT/'tools/dev/authority_download_load_probe.lua').read_text()
  code=code.replace("local state='initial';local failed=false\n", "local state='initial';local failed=false\nlocal registry_status=nil\n")
  code=code.replace(" elseif state=='observing' then\n", " elseif state=='observing' then\n  local check={expected='"+self.status[1]+'|'+str(self.status[2])+"'}\n  if not registry_status:ready() then return end\n")
  (self.ui/'authority_download_load_probe.lua').write_text(code)
  (self.ui/'recovery_registry_status.lua').write_text('-- probe\n');(self.md/'authority_ship_registry.xml').write_text('<mdscript/>')
 def install(self):return subject.install(self.case,self.profile,self.status,self.settings)
 def test_overlay_is_additive_protected_and_redacted(self):
  before=(self.md/'authority_ship_registry.xml').read_bytes();control=(self.ui/'authority_two_x4_participant_probe.lua').read_text()
  result=self.install();self.assertEqual((self.md/'authority_ship_registry.xml').read_bytes(),before)
  self.assertEqual(len(result.paths),len(set(result.paths)))
  for p in result.paths:self.assertTrue(p.is_file())
  for name in subject.MD:ET.parse(self.md/name)
  installed=(self.ui/'authority_two_x4_participant_probe.lua').read_text()
  self.assertEqual(installed.count("SetScript('onUpdate'"),1);self.assertIn('assert(state:on_update())',installed)
  self.assertIn('assert(state:on_update())',control);self.assertIn('client_motion:tick()',installed)
  self.assertEqual((self.lab/'ui.xml').read_text().count('ui/client_motion_event_router.lua'),1)
  self.assertIn('state==\'done\' and not failed',(self.ui/'authority_download_load_probe.lua').read_text())
  if shutil.which('luajit'):
   for p in (self.ui/'authority_two_x4_participant_probe.lua',self.ui/'authority_download_load_probe.lua',*(self.ui/name for _,name in subject.MODULES)):
    subprocess.run(['luajit','-b',str(p),'/dev/null'],check=True,capture_output=True)
  result.redact();redacted=(self.ui/'config.lua').read_text()
  for key in subject.SECRET_FIELDS:
   self.assertNotIn(self.settings[key],redacted);self.assertIn('authority_client_motion_'+key+'="redacted"',redacted)
  with self.assertRaises(ValueError):result.redact()
 def test_refusals_do_not_mutate_input_files(self):
  files=(self.ui/'config.lua',self.lab/'ui.xml',self.ui/'authority_two_x4_participant_probe.lua',self.ui/'authority_download_load_probe.lua')
  original=[p.read_bytes() for p in files]
  for key,value in (('port',1234),('index',101),('nonce','1'*32),('lease','a'*32),('timeout',float('nan'))):
   with self.subTest(key=key):
    old=self.settings[key];self.settings[key]=value
    with self.assertRaises(ValueError):self.install()
    self.settings[key]=old;self.assertEqual([p.read_bytes() for p in files],original)
  with self.assertRaises(ValueError):subject.install(self.case,self.profile,('ready','c'*32,99,'d'*64),self.settings)
  self.assertEqual([p.read_bytes() for p in files],original)
 def test_redaction_rejects_replaced_config(self):
  result=self.install();config=self.ui/'config.lua';replacement=self.ui/'replacement';replacement.write_bytes(config.read_bytes());os.replace(replacement,config)
  with self.assertRaises(ValueError):result.redact()
 def test_redaction_short_reads_and_changed_file(self):
  result=self.install();config=self.ui/'config.lua';original=config.read_bytes();real_read=os.read
  with mock.patch.object(subject.os,'read',side_effect=lambda fd,n:real_read(fd,min(n,17))):result.redact()
  self.assertTrue(config.read_text().endswith('}\n'))
  config.write_bytes(original)
  calls=0
  def short_then_eof(fd,n):
   nonlocal calls
   calls+=1
   return real_read(fd,min(n,17)) if calls==1 else b''
  with mock.patch.object(subject.os,'read',side_effect=short_then_eof):
   with self.assertRaises(ValueError):result.redact()
  self.assertEqual(config.read_bytes(),original)
  def mutate(fd,n):
   data=real_read(fd,n)
   with config.open('ab') as out:out.write(b'changed')
   return data
  with mock.patch.object(subject.os,'read',side_effect=mutate):
   with self.assertRaises(ValueError):result.redact()
  self.assertEqual(config.read_bytes(),original+b'changed')
 @unittest.skipUnless(os.name=='posix' and shutil.which('luajit') and shutil.which('cc'),'LuaJIT and C compiler required')
 def test_lua_composition_and_late_event_fence(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'abi.so';subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/replica_motion_binding_abi.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True)
   for mode in ('good','wrong_index','queued_empty','queued_oversize','late_empty','late_oversize','race_empty','race_oversize'):
    subprocess.run(['luajit','tests/authority_recovered_client_motion.lua',mode],cwd=ROOT,check=True,capture_output=True,timeout=5,env=dict(os.environ,LD_PRELOAD=str(lib)))
 @unittest.skipUnless(os.name=='posix' and shutil.which('luajit') and shutil.which('cc'),'LuaJIT and C compiler required')
 def test_player_loss_before_and_after_motion_start(self):
  self.install()
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'abi.c';lib=Path(tmp)/'abi.so'
   original=(ROOT/'tests/fixtures/replica_motion_binding_abi.c').read_text()
   old='bool IsPlayerValid(void){return true;}'
   self.assertEqual(original.count(old),1)
   source.write_text(original.replace(old,'static bool player_valid=true; void TestPlayerValid(bool v){player_valid=v;} bool IsPlayerValid(void){return player_valid;}'))
   subprocess.run(['cc','-O2','-shared','-fPIC',str(source),'-o',str(lib)],check=True,capture_output=True)
   subprocess.run(['luajit','tests/authority_recovered_client_motion_control.lua',str(self.ui/'authority_two_x4_participant_probe.lua')],cwd=ROOT,check=True,capture_output=True,timeout=5,env=dict(os.environ,LD_PRELOAD=str(lib)))
if __name__=='__main__':unittest.main()
