"""Disposable overlay and actual Lua composition; no X4 is started."""
from pathlib import Path
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_load_live as load
import authority_download_load_live as download
import authority_recovered_client_motion_install as subject
import authority_recovered_client_registry as registry
import authority_recovered_server_client as recovered_client
import authority_two_x4_identity_live as identity
import authority_two_x4_resume_live as participant

class Install(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.case=Path(self.temp.name)/'case';self.profile=self.case/'home/.config/EgoSoft/X4/45841'
  (self.profile/'save').mkdir(parents=True)
  self.lab=self.case/'extensions/x4_lan_lab';self.ui=self.lab/'ui';self.md=self.lab/'md'
  self.ui.mkdir(parents=True);self.md.mkdir()
  self.status=('ready','c'*32,100,'d'*64)
  self.settings={'port':2345,'lease':'1'*32,'attempt':'2'*32,'generation':'3'*32,'nonce':'4'*32,'router_generation':'5'*32,'timeout':5,'index':42}
  # Use the real production load installer: it encodes ticket strings as Lua
  # decimal byte escapes, which hand-written hex fixtures previously missed.
  (self.ui/'native_gate_snapshot.lua').write_text('')
  (self.md/'native_gate_battle.xml').write_text('')
  (self.ui/'config.lua').write_text('')
  ticket={'world_epoch':'e'*32,'connection_handle':1,'baseline_id':2,'load_generation':1,
          'checkpoint_id':'checkpoint-'+'6'*32,'sha256':'7'*64,'attempt_id':'f'*32,'slot':'save_009'}
  config=download.install_probe(self.case,self.profile,ticket)
  cfg=config.read_text();config.write_text(cfg[:-2]+',authority_participant_port=1234,authority_participant_lease="'+'a'*32+'"}\n')
  (self.lab/'ui.xml').write_text('<ui>\n    <file name="ui/authority_download_load_probe.lua" />\n    <file name="ui/local_udp_module.lua" />\n    <file name="ui/authority_two_x4_participant_probe.lua" />\n</ui>\n')
  (self.ui/'local_udp_module.lua').write_bytes(participant.local_udp_loader_bytes())
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
  manifest=(self.lab/'ui.xml').read_text()
  self.assertEqual(manifest.count('ui/local_udp_module.lua'),1)
  self.assertLess(manifest.index('ui/local_udp_module.lua'),manifest.index('ui/authority_recovered_client_motion.lua'))
  self.assertLess(manifest.index('ui/local_udp_module.lua'),manifest.index('ui/authority_two_x4_participant_probe.lua'))
  self.assertNotIn('ui/saved_motion_apply.lua',manifest)
  self.assertFalse((self.md/'authority_saved_motion_apply.xml').exists())
  self.assertNotIn('ui/player_sector_interest.lua',manifest)
  self.assertFalse((self.md/'authority_player_sector_interest.xml').exists())
  self.assertNotIn('player_sector=',installed)
  self.assertIn('state==\'done\' and not failed',(self.ui/'authority_download_load_probe.lua').read_text())
  if shutil.which('luajit'):
   for p in (self.ui/'authority_two_x4_participant_probe.lua',self.ui/'authority_download_load_probe.lua',*(self.ui/name for _,name in subject.MODULES)):
    subprocess.run(['luajit','-b',str(p),'/dev/null'],check=True,capture_output=True)
  result.redact();redacted=(self.ui/'config.lua').read_text()
  for key in subject.SECRET_FIELDS:
   self.assertNotIn(self.settings[key],redacted);self.assertIn('authority_client_motion_'+key+'="redacted"',redacted)
  with self.assertRaises(ValueError):result.redact()
 def test_opt_in_recovery_saved_apply_overlay(self):
  self.status=('ready',subject.RECOVERY_APPLY_EPOCH,10082,'d'*64)
  loader=self.ui/'authority_download_load_probe.lua'
  loader.write_text(loader.read_text().replace("expected='"+'c'*32+'|100',"expected='"+self.status[1]+'|10082'))
  self.settings.update(index=1318,saved_apply_fixture=subject.RECOVERY_APPLY_FIXTURE)
  result=self.install()
  self.assertIn(self.ui/'saved_motion_apply.lua',result.paths)
  self.assertIn(self.md/'authority_saved_motion_apply.xml',result.paths)
  self.assertEqual((self.ui/'saved_motion_apply.lua').read_bytes(),(ROOT/subject.RECOVERY_APPLY_MODULE[0]).read_bytes())
  self.assertEqual((self.md/'authority_saved_motion_apply.xml').read_bytes(),(ROOT/'tools/dev'/subject.RECOVERY_APPLY_MD).read_bytes())
  ET.parse(self.md/'authority_saved_motion_apply.xml')
  manifest=(self.lab/'ui.xml').read_text()
  self.assertLess(manifest.index('ui/saved_motion_apply.lua'),manifest.index('ui/authority_recovered_client_motion.lua'))
  self.assertIn('saved_apply_fixture=cfg.authority_client_motion_saved_apply_fixture',
                (self.ui/'authority_two_x4_participant_probe.lua').read_text())
  self.assertIn('authority_client_motion_saved_apply_fixture="recovery_enh_870"',(self.ui/'config.lua').read_text())
 def prepare_playback(self):
  self.status=('ready',subject.RECOVERY_APPLY_EPOCH,10082,'d'*64)
  loader=self.ui/'authority_download_load_probe.lua'
  loader.write_text(loader.read_text().replace("expected='"+'c'*32+'|100',"expected='"+self.status[1]+'|10082'))
  self.settings.update(index=1318,saved_playback_fixture=subject.RECOVERY_APPLY_FIXTURE)
 def test_opt_in_saved_playback_installs_runtime_in_existing_owner(self):
  self.prepare_playback()
  result=self.install()
  for source,name in (subject.RECOVERY_APPLY_MODULE,subject.RECOVERY_PLAYBACK_MODULE):
   self.assertIn(self.ui/name,result.paths)
   self.assertEqual((self.ui/name).read_bytes(),(ROOT/source).read_bytes())
  manifest=(self.lab/'ui.xml').read_text()
  self.assertLess(manifest.index('ui/motion_playback.lua'),manifest.index('ui/authority_recovered_client_motion.lua'))
  control=(self.ui/'authority_two_x4_participant_probe.lua').read_text()
  self.assertEqual(control.count("SetScript('onUpdate'"),1)
  self.assertIn('saved_playback_fixture=cfg.authority_client_motion_saved_playback_fixture',control)
  self.assertLess(control.index('client playback STOP required before pause'),control.index("assert(state:submit('isolated-client'"))
  self.assertFalse((self.md/'authority_saved_motion_apply.xml').exists())
  result.redact()
 def test_saved_playback_rejects_context_conflicts_before_mutation(self):
  self.prepare_playback()
  files=(self.ui/'config.lua',self.lab/'ui.xml',self.ui/'authority_two_x4_participant_probe.lua',self.ui/'authority_download_load_probe.lua')
  before=[path.read_bytes() for path in files]
  valid=dict(self.settings)
  for change in ({'saved_playback_fixture':None},{'saved_playback_fixture':'other'},
                 {'saved_apply_fixture':subject.RECOVERY_APPLY_FIXTURE},{'index':1317},
                 {'indices':[1318]}):
   with self.subTest(change=change):
    self.settings=dict(valid,**change)
    with self.assertRaises(ValueError):self.install()
    self.assertEqual([path.read_bytes() for path in files],before)
    self.assertFalse((self.ui/'motion_playback.lua').exists())
  self.settings=valid
  self.status=('ready','c'*32,10082,'d'*64)
  with self.assertRaises(ValueError):self.install()
  self.assertEqual([path.read_bytes() for path in files],before)
 def test_saved_playback_runtime_and_pre_dispatch_pause_fence(self):
  self.prepare_playback();self.install()
  with tempfile.TemporaryDirectory() as directory:
   library=Path(directory)/'abi.so'
   subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/saved_motion_apply_abi.c','-o',str(library)],cwd=ROOT,check=True,capture_output=True)
   environment=dict(os.environ,LD_PRELOAD=str(library))
   for mode in ('good','bounded','uncertain','docking','fixture','zone','paused_initial','sector','index','sequence','source_time','bind2','context'):
    with self.subTest(mode=mode):
     result=subprocess.run(['luajit','tests/authority_recovered_client_playback.lua',mode],cwd=ROOT,capture_output=True,text=True,timeout=5,env=environment)
     self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   for mode in ('ready','stopped'):
    with self.subTest(pause_mode=mode):
     result=subprocess.run(['luajit','tests/authority_recovered_client_playback_pause.lua',str(self.ui/'authority_two_x4_participant_probe.lua'),mode],cwd=ROOT,capture_output=True,text=True,timeout=5,env=environment)
     self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_saved_apply_combines_with_player_sector_after_bound(self):
  self.status=('ready',subject.RECOVERY_APPLY_EPOCH,10082,'d'*64)
  loader=self.ui/'authority_download_load_probe.lua'
  text=loader.read_text().replace("expected='"+'c'*32+'|100',"expected='"+self.status[1]+'|10082')
  marker='  local check={'
  registry="  registry_status=assert(X4LAN_RECOVERY_REGISTRY_STATUS.new({nonce='"+'8'*32+"',expected='example'}))\n"
  self.assertEqual(text.count(marker),1);loader.write_text(text.replace(marker,registry+marker))
  self.settings.update(index=1318,saved_apply_fixture=subject.RECOVERY_APPLY_FIXTURE,
                       player_sector={'incarnation':'9'*32,'nonce':'0'*32,'after_bound':True})
  result=self.install()
  control=(self.ui/'authority_two_x4_participant_probe.lua').read_text()
  self.assertIn('saved_apply_fixture=cfg.authority_client_motion_saved_apply_fixture',control)
  self.assertIn('nonce=cfg.authority_client_motion_player_sector_nonce,after_bound=true',control)
  self.assertIn(self.ui/'saved_motion_apply.lua',result.paths)
  self.assertIn(self.ui/'player_sector_interest.lua',result.paths)
 def test_saved_apply_refuses_wrong_identity_before_mutation(self):
  paths=(self.ui/'config.lua',self.lab/'ui.xml',self.ui/'authority_two_x4_participant_probe.lua',self.ui/'authority_download_load_probe.lua')
  before=[p.read_bytes() for p in paths]
  self.settings['saved_apply_fixture']=subject.RECOVERY_APPLY_FIXTURE
  for value in (None,False,'unknown',subject.RECOVERY_APPLY_FIXTURE):
   self.settings['saved_apply_fixture']=value
   with self.subTest(value=value),self.assertRaises(ValueError):self.install()
   self.assertEqual([p.read_bytes() for p in paths],before)
  self.assertFalse((self.ui/'saved_motion_apply.lua').exists())
 @unittest.skipUnless(os.name=='posix' and shutil.which('luajit') and shutil.which('cc'),'LuaJIT and C compiler required')
 def test_recovery_saved_apply_lua_composition(self):
  with tempfile.TemporaryDirectory() as tmp:
   lib=Path(tmp)/'abi.so'
   subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/saved_motion_apply_abi.c','-o',str(lib)],cwd=ROOT,check=True,capture_output=True)
   for mode in ('good','sector','apply_first','wrong_sequence','preflight_fault','repeat_preflight','repeat_apply',
                'timing_fault','timing_success','timing_expired','timing_clock_error','timing_clock_infinite','timing_clock_backwards','timing_log_throws'):
    with self.subTest(mode=mode):
     subprocess.run(['luajit','tests/authority_recovered_client_saved_apply.lua',mode],cwd=ROOT,check=True,capture_output=True,timeout=5,env=dict(os.environ,LD_PRELOAD=str(lib)))
 def test_refusals_do_not_mutate_input_files(self):
  files=(self.ui/'config.lua',self.lab/'ui.xml',self.ui/'authority_two_x4_participant_probe.lua',self.ui/'authority_download_load_probe.lua')
  original=[p.read_bytes() for p in files]
  for key,value in (('port',1234),('index',101),('nonce','1'*32),('lease','a'*32),
                    ('generation','e'*32),('attempt','f'*32),('timeout',float('nan'))):
   with self.subTest(key=key):
    old=self.settings[key];self.settings[key]=value
    with self.assertRaises(ValueError):self.install()
    self.settings[key]=old;self.assertEqual([p.read_bytes() for p in files],original)
  with self.assertRaises(ValueError):subject.install(self.case,self.profile,('ready','c'*32,99,'d'*64),self.settings)
  self.assertEqual([p.read_bytes() for p in files],original)
 def test_ticket_token_encodings_and_ambiguity(self):
  for value in ('e'*32,load.lua_literal('e'*32)[1:-1]):
   self.assertEqual(subject.read_ticket_token('authority_ticket={world_epoch="'+value+'"}','world_epoch'),'e'*32)
  for value in ('checkpoint-'+'6'*32,load.lua_literal('checkpoint-'+'6'*32)[1:-1]):
   self.assertEqual(subject.read_ticket_token('ticket={checkpoint_id="'+value+'"}','checkpoint_id',prefix='checkpoint-'),'6'*32)
  for text in ('world_epoch="'+r'\999'*32+'"', 'world_epoch="'+r'\097'*31+'"',
               'world_epoch="'+r'\122'*32+'"', 'world_epoch="'+'e'*32+'",world_epoch="'+'f'*32+'"'):
   with self.subTest(text=text),self.assertRaises(ValueError):subject.read_ticket_token('ticket={'+text+'}','world_epoch')
 def test_real_recovery_client_installation_sequence(self):
  case=Path(self.temp.name)/'production'/'case'
  profile=case/'home/.config/EgoSoft/X4/45841'
  (profile/'save').mkdir(parents=True)
  lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
  ui.mkdir(parents=True);md.mkdir();(lab/'native').mkdir()
  (ui/'native_gate_snapshot.lua').write_text('')
  (md/'native_gate_battle.xml').write_text('')
  (ui/'config.lua').write_text('')
  ticket={'world_epoch':'e'*32,'connection_handle':1,'baseline_id':2,'load_generation':1,
          'checkpoint_id':'checkpoint-'+'6'*32,'sha256':'7'*64,'attempt_id':'f'*32,'slot':'save_009'}
  download.install_probe(case,profile,ticket)
  identity.inject(case,'load')
  participant=recovered_client.ServerClient(time.monotonic()+10,case,keep_worker=True)
  self.addCleanup(participant.cleanup_diagnostic)
  fake_library=Path(self.temp.name)/'server-net.so';fake_library.write_bytes(b'not loaded in this test')
  participant.server_library=fake_library
  participant.install(case)
  registry.install(case,'8'*32,self.status)
  shutil.copyfile(ROOT/'tools/dev/authority_registry_witness.xml',md/'authority_registry_witness.xml')
  motion_socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  self.addCleanup(motion_socket.close);motion_socket.bind(('127.0.0.1',0))
  settings=dict(self.settings,port=motion_socket.getsockname()[1],
                player_sector={'incarnation':'9'*32,'nonce':'0'*32})
  installation=subject.install(case,profile,self.status,settings)
  self.assertTrue(all(path.is_file() for path in installation.paths))
  self.assertIn(ui/'local_udp_module.lua',participant.protected(case))
  manifest=(lab/'ui.xml').read_text()
  self.assertEqual(manifest.count('ui/player_sector_interest.lua'),1)
  self.assertLess(manifest.index('ui/player_sector_interest.lua'),manifest.index('ui/authority_recovered_client_motion.lua'))
  self.assertIn(ui/'player_sector_interest.lua',installation.paths)
  self.assertIn(md/'authority_player_sector_interest.xml',installation.paths)
  self.assertEqual((ui/'player_sector_interest.lua').read_bytes(),(ROOT/subject.PLAYER_SECTOR_MODULE[0]).read_bytes())
  self.assertEqual((md/'authority_player_sector_interest.xml').read_bytes(),(ROOT/'tools/dev'/subject.PLAYER_SECTOR_MD).read_bytes())
  control=(ui/'authority_two_x4_participant_probe.lua').read_text()
  self.assertIn('player_sector={incarnation=cfg.authority_client_motion_player_sector_incarnation,nonce=cfg.authority_client_motion_player_sector_nonce}',control)
  self.assertEqual(control.count("SetScript('onUpdate'"),1)
  installation.redact();participant.redact()
  redacted=(ui/'config.lua').read_text()
  for name,value in settings['player_sector'].items():
   self.assertNotIn(value,redacted)
   self.assertIn('authority_client_motion_player_sector_'+name+'="redacted"',redacted)
 def test_player_sector_context_refuses_collisions_and_ambiguous_registry(self):
  loader=self.ui/'authority_download_load_probe.lua'
  original=loader.read_text()
  hook='  local check={'
  registry="  registry_status=assert(X4LAN_RECOVERY_REGISTRY_STATUS.new({nonce='"+'8'*32+"',expected='example'}))\n"
  self.assertEqual(original.count(hook),1)
  loader.write_text(original.replace(hook,registry+hook))
  files=(self.ui/'config.lua',self.lab/'ui.xml',self.ui/'authority_two_x4_participant_probe.lua',loader)
  before=[p.read_bytes() for p in files]
  self.settings['player_sector']={'incarnation':'9'*32,'nonce':'0'*32}
  invalid=[None,{}, {'incarnation':'9'*32,'nonce':'9'*32},
           {'incarnation':'9'*32,'nonce':'0'*31}, {'incarnation':'9'*32,'nonce':'0'*32,'extra':1}]
  invalid += [{'incarnation':'9'*32,'nonce':'0'*32,'after_bound':value} for value in (False, 1, None, 'true')]
  invalid += [{'incarnation':'9'*32,'nonce':token} for token in
              ('1'*32,'2'*32,'3'*32,'4'*32,'5'*32,'c'*32,'a'*32,'e'*32,'f'*32,'8'*32,'6'*32)]
  for value in invalid:
   with self.subTest(value=value):
    self.settings['player_sector']=value
    with self.assertRaises(ValueError):self.install()
    self.assertEqual([p.read_bytes() for p in files],before)
    self.assertFalse((self.ui/'player_sector_interest.lua').exists())
  self.settings['player_sector']={'incarnation':'9'*32,'nonce':'0'*32}
  loader.write_text(original.replace(hook,registry+registry+hook))
  before=[p.read_bytes() for p in files]
  with self.assertRaises(ValueError):self.install()
  self.assertEqual([p.read_bytes() for p in files],before)
 def test_player_sector_after_bound_install_and_token_redaction(self):
  loader=self.ui/'authority_download_load_probe.lua'
  original=loader.read_text();hook='  local check={'
  registry="  registry_status=assert(X4LAN_RECOVERY_REGISTRY_STATUS.new({nonce='"+'8'*32+"',expected='example'}))\n"
  loader.write_text(original.replace(hook,registry+hook))
  self.settings['player_sector']={'incarnation':'9'*32,'nonce':'0'*32,'after_bound':True}
  installation=self.install()
  control=(self.ui/'authority_two_x4_participant_probe.lua').read_text()
  self.assertIn('nonce=cfg.authority_client_motion_player_sector_nonce,after_bound=true',control)
  installation.redact()
  config=(self.ui/'config.lua').read_text()
  self.assertNotIn('9'*32,config);self.assertNotIn('0'*32,config)
 def test_loader_missing_changed_or_misordered_is_rejected_before_mutation(self):
  loader=self.ui/'local_udp_module.lua';manifest=self.lab/'ui.xml'
  original_loader=loader.read_bytes();original_manifest=manifest.read_text()
  inputs=(self.ui/'config.lua',manifest,self.ui/'authority_two_x4_participant_probe.lua',self.ui/'authority_download_load_probe.lua')
  loader_hook='    <file name="ui/local_udp_module.lua" />\n'
  control_hook='    <file name="ui/authority_two_x4_participant_probe.lua" />\n'
  for mode in ('missing','changed','missing_manifest','duplicate_manifest','alternate_duplicate','misordered_manifest'):
   with self.subTest(mode=mode):
    loader.write_bytes(original_loader);manifest.write_text(original_manifest)
    if mode=='missing':loader.unlink()
    elif mode=='changed':loader.write_bytes(b'changed')
    elif mode=='missing_manifest':manifest.write_text(original_manifest.replace(loader_hook,''))
    elif mode=='duplicate_manifest':manifest.write_text(original_manifest.replace(loader_hook,loader_hook+loader_hook))
    elif mode=='alternate_duplicate':manifest.write_text(original_manifest.replace(loader_hook,loader_hook+"  <file name='ui/local_udp_module.lua'/>\n"))
    else:manifest.write_text(original_manifest.replace(loader_hook,'').replace(control_hook,control_hook+loader_hook))
    before=[p.read_bytes() for p in inputs]
    with self.assertRaises(ValueError):self.install()
    self.assertEqual([p.read_bytes() for p in inputs],before)
    self.assertFalse((self.ui/'authority_recovered_client_motion.lua').exists())
 @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
 def test_both_client_owners_select_only_their_platform_loader(self):
  for platform in ('Linux','Windows','unsupported'):
   with self.subTest(platform=platform):
    subprocess.run(['luajit','tests/authority_recovered_client_udp_loader.lua',platform],
                   cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
 def test_redaction_rejects_replaced_config(self):
  result=self.install();config=self.ui/'config.lua';replacement=self.ui/'replacement';replacement.write_bytes(config.read_bytes());os.replace(replacement,config)
  with self.assertRaises(ValueError):result.redact()
 def test_bounded_candidate_list_install_and_refusal(self):
  del self.settings['index'];self.settings['indices']=[42,43]
  cfg=self.ui/'config.lua';before=cfg.read_bytes()
  for invalid in ([],[42,42],[0],[101],list(range(1,34)),[True],(42,43)):
   with self.subTest(invalid=invalid):
    self.settings['indices']=invalid
    with self.assertRaises(ValueError):self.install()
    self.assertEqual(cfg.read_bytes(),before)
  self.settings['indices']=[42,43];result=self.install()
  self.assertIn('authority_client_motion_indices={42,43}',cfg.read_text())
  self.assertIn('indices=cfg.authority_client_motion_indices',(self.ui/'authority_two_x4_participant_probe.lua').read_text())
  result.redact()
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
   for mode in ('good','wrong_index','queued_empty','queued_oversize','late_empty','late_oversize','race_empty','race_oversize','list_good','list_unknown','list_switch','list_second'):
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
