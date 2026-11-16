"""Offline checks of the two-profile archived readiness harness."""
import importlib.util
import os
from pathlib import Path
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock,patch
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pair_live',ROOT/'tools/dev/authority_sector_pair_live.py')
pair=importlib.util.module_from_spec(spec);spec.loader.exec_module(pair)

class PairTests(unittest.TestCase):
 def test_probe(self):
  for mode in ('ok','disabled','invalid','dispatch','wrong_id','wrong_epoch','wrong_macro','wrong_actor','pause_loss','after_pause','duplicate','refused','timeout','slow_export','slow_ffi','slow_dispatch','slow_last_guard'):
   with self.subTest(mode=mode):subprocess.run(['luajit','tests/authority_sector_pair_ready.lua',mode],cwd=ROOT,check=True,capture_output=True)
 def test_overlay_has_no_mutator_and_one_owner(self):
  with tempfile.TemporaryDirectory() as t:
   case=Path(t)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
   ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
   for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
   ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,checkpoint_id=pair.base.archive.CHECKPOINT_ID,sha256=pair.base.archive.SHA256,attempt_id='b'*32,slot='save_009')
   protected=pair.install(case,profile,ticket,'server','c'*32,['sector_a','sector_b'],120)
   owner=(ui/'authority_download_load_probe.lua').read_text();self.assertEqual(owner.count("SetScript('onUpdate'"),1);self.assertIn('X4LAN_SECTOR_PAIR_TICK()',owner)
   self.assertIn(md/'authority_sector_pair_ready.xml',protected);self.assertIn(ui/'authority_sector_pair_ready.lua',protected)
   contents=''.join(p.read_text() for p in md.glob('*.xml'))
   self.assertNotIn('<create_ship',contents);self.assertNotIn('<set_object_velocity',contents)
   self.assertNotIn('authority_ship_create_receiver.xml',{p.name for p in md.iterdir()})
 def test_readiness_evidence(self):
  with patch.object(pair.base,'check_log_bytes',return_value={'reported_game_time':3.0}):
   tag=pair.TAG;pause=pair.base.load.TAG.decode()+'pause_observed|ticket';n='a'*32
   ready=tag+'READY role=server nonce='+n+' game=3'
   raw=lambda lines:('\n'.join(lines)+'\n').encode()
   self.assertEqual(pair.validate(raw([pause,ready]),{},'server',n)['baseline_registry_count'],2)
   self.assertIsNone(pair.validate(raw([pause]),{},'server',n,partial=True))
   for rows in ([ready,pause],[pause,ready,ready],[pause,ready.replace('server','client')],[pause,ready.replace('game=3','game=4')],[pause,ready,tag+'ERROR late']):
    with self.assertRaises(ValueError):pair.validate(raw(rows),{},'server',n)
 def simulate(self,mode):
  with tempfile.TemporaryDirectory() as t,ExitStack() as stack:
   root=Path(t);game=root/'game';(game/'extensions').mkdir(parents=True);(game/'X4').write_text('')
   auth=root/'auth';auth.write_text('');store=root/'archive'/'checkpoints';store.mkdir(parents=True);out=root/'out'
   args=SimpleNamespace(out=out,store=store,timeout=120,seed=1,game=game,display=':0')
   user=SimpleNamespace(pw_dir=str(root),pw_uid=1000,pw_gid=1000,pw_name='tester')
   cp=SimpleNamespace(checkpoint_id=pair.base.archive.CHECKPOINT_ID,sha256=pair.base.archive.SHA256,size=10)
   set_=lambda obj,name,value:stack.enter_context(patch.object(obj,name,value))
   set_(pair.os,'geteuid',lambda:1000);stack.enter_context(patch.dict(pair.os.environ,{'XAUTHORITY':str(auth)}))
   set_(pair.base.snapshot,'output_path',lambda _:out);set_(pair.base.base,'local_directory',lambda _:store)
   set_(pair.base.archive,'DEFAULT_STORE',store);fingerprint_calls=[0]
   def fingerprints(_):
    fingerprint_calls[0]+=1
    return {'changed':1} if mode=='source_changed' and fingerprint_calls[0]>=4 else {'stable':1}
   set_(pair.base.archive,'_path_fingerprints',fingerprints)
   set_(pair.base.archive,'verify',lambda _:{'sha256':cp.sha256,'size':cp.size})
   set_(pair,'CheckpointStore',lambda _:SimpleNamespace(latest_confirmed=lambda:cp))
   set_(pair.saved,'verify',lambda *_:{'slots':[{'index':1,'sector_macro':'sector_a'},{'index':2,'sector_macro':'sector_b'}],'sector_macros_unique_in_saved_universe':True})
   set_(pair.base.live,'EXE_SHA',cp.sha256);set_(pair.base.live,'sha',lambda _:cp.sha256)
   set_(pair.base.live,'x4_executables',lambda:[]);set_(pair.shutil,'which',lambda _:'/bin/bwrap')
   set_(pair.pwd,'getpwuid',lambda _:user);set_(pair.base.live,'steam_identity',lambda *_:('stable',))
   def prepare(roleout,*_):
    case=roleout/'case';profile=case/'profile';(profile/'save').mkdir(parents=True);return case,profile,[],case/'lock'
   set_(pair.base.snapshot,'prepare_case',prepare);set_(pair.base,'check_origin_scripts',lambda *_:None);set_(pair.base,'MD',())
   def stage(_,__,profile):
    target=profile/'save'/'save_009.xml.gz';target.write_bytes(b'save');return cp,target
   set_(pair.base.base,'stage_checkpoint',stage);set_(pair,'install',lambda *_:[])
   set_(pair.readonly,'readonly_save_command',lambda *_:['bwrap','--die-with-parent'])
   def stable(path,*_,**kwargs):
    raw=b'late' if mode=='late_log' and path.name=='engine-output.log' and 'client' in str(path) else b'ok'
    return ((1,2,3,4,5),cp.sha256,raw)
   set_(pair.base,'stable_read',stable);log_calls={'server':0,'client':0}
   def read_log(path,_):
    role='server' if 'server' in str(path) else 'client';log_calls[role]+=1
    if mode=='growing_log':
     if role=='client' and log_calls[role]==1:return None
     if role=='server' and log_calls[role]==2:return None
     if role=='server' and log_calls[role]>=3:raise ValueError('later source fault')
    return b'ok',((1,2),2,b'digest')
   set_(pair.base,'read_live_log',read_log)
   set_(pair.base,'log_continuity',lambda *_:None);set_(pair,'fault',lambda _:False)
   def validate(raw,ticket,role,nonce,**kwargs):
    if raw==b'late':raise ValueError('late callback')
    return {'role':role,'baseline_registry_count':2}
   set_(pair,'validate',validate)
   lockfile=root/'lockfd';lockfile.write_text('');lockfd=os.open(lockfile,os.O_RDONLY)
   set_(pair.base.live,'create_lock_target',lambda *_:(lockfd,'lockstat'))
   release=set_(pair.base.live,'release_lock_target',Mock(side_effect=lambda *_:os.close(lockfd)))
   handlers={}
   def install_signal(number,handler):handlers[number]=handler;return pair.signal.SIG_DFL
   set_(pair.signal,'signal',install_signal)
   procs=[]
   def spawn(cmd,log,owned):
    proc=Mock(pid=100+len(procs));procs.append(proc);owned.append([proc,7])
    if mode=='signal_second' and len(procs)==2:handlers[pair.signal.SIGTERM](pair.signal.SIGTERM,None)
    return proc,7
   set_(pair.owned,'spawn_owned_gated',spawn)
   set_(pair.base.load,'game_identity',lambda proc,*_:(proc.pid,7,1,2))
   def stop(proc,_):return [proc.pid] if mode=='survivor' and proc.pid==100 else []
   stopping=set_(pair.base.snapshot,'stop_owned',Mock(side_effect=stop))
   result=pair.run(args)
   self.assertEqual(len(procs),2);self.assertEqual(stopping.call_count,2)
   self.assertTrue((out/'result.json').is_file())
   if mode=='ok':
    self.assertTrue(result['success']);self.assertTrue(result['owned_cleanup_confirmed']);release.assert_called_once()
    self.assertFalse(result['experiment_network_requested']);self.assertFalse(result['create_requested'])
   else:
    self.assertFalse(result['success'])
    if mode=='survivor':release.assert_not_called();self.assertIn('lock retained: stop unconfirmed',result['cleanup_errors'])
    else:release.assert_called_once()
   return result
 def test_cleanup_and_signal_fencing(self):
  for mode in ('ok','signal_second','survivor','late_log','source_changed','growing_log'):
   with self.subTest(mode=mode):self.simulate(mode)

if __name__=='__main__':unittest.main()
