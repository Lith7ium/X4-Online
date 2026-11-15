"""Synthetic checks for the isolated checkpoint load harness; no X4 is launched."""
import gzip
import json
from decimal import Decimal
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/dev'))
import authority_load_live as live
from authority.checkpoints import CheckpointStore


class LoadHarnessTests(unittest.TestCase):
    def setup_cycles(self, root):
        origin = root/'source'; cycle_id = 'a'*32
        profile = root/'case/home/.config/EgoSoft/X4/45841';(profile/'save').mkdir(parents=True)
        (profile/'content.xml').write_text('<content/>')
        old_profile = origin/'case/home/.config/EgoSoft/X4/45841';old_profile.mkdir(parents=True)
        (old_profile/'content.xml').write_text('<content/>')
        config = origin/'case/extensions/x4_lan_lab/ui/config.lua';config.parent.mkdir(parents=True)
        config.write_text(f'authority_control_lease="redacted", authority_cycle_id="{cycle_id}"')
        (old_profile/'engine-output.log').write_text(''.join('[X4LAN] '+marker+'\n' for marker in live.CYCLE_MARKERS))
        rows=[]; checkpoints=[]
        for cycle in (1,2):
            folder=origin/'checkpoints'/f'cycle-{cycle}';folder.mkdir(parents=True)
            source=root/f'save-{cycle}.gz'
            source.write_bytes(gzip.compress((f'<savegame><info><save name="X4 Authority cycle {cycle} {cycle_id}"/>'
                                              f'<game time="{cycle * 10}"/></info></savegame>').encode()))
            checkpoint=CheckpointStore(folder).publish(source);checkpoints.append(checkpoint)
            rows.append({'cycle':cycle, 'checkpoint_id':checkpoint.checkpoint_id, 'sha256':checkpoint.sha256,
                         'size':checkpoint.size,'game_time':str(cycle*10),'file_verified':True})
        record={'success':True,'resume_confirmed':True,'owned_processes_remaining':[],'cycles':rows}
        (origin/'result.json').write_text(json.dumps(record))
        return origin, checkpoints, profile

    def setup_store(self, root):
        origin = root/'source'; store_dir = origin/'checkpoints';store_dir.mkdir(parents=True)
        source = root/'save.gz';source.write_bytes(gzip.compress(
            b'<savegame><info><save name="X4 Authority isolated checkpoint"/><game time="10.250"/></info></savegame>'))
        store = CheckpointStore(store_dir);checkpoint = store.publish(source)
        profile = root/'case/home/.config/EgoSoft/X4/45841';(profile/'save').mkdir(parents=True)
        (profile/'content.xml').write_text('<content/>')
        old_profile = origin/'case/home/.config/EgoSoft/X4/45841';old_profile.mkdir(parents=True)
        (old_profile/'content.xml').write_text('<content/>')
        record = {'success':True, 'native_save_event':True, 'file_verified':True, 'resume_confirmed':True,
                  'owned_processes_remaining':[], 'checkpoint_id':checkpoint.checkpoint_id,
                  'sha256':checkpoint.sha256, 'size':checkpoint.size}
        (origin/'result.json').write_text(json.dumps(record))
        return store_dir, store, checkpoint, profile

    def test_staging_and_origin_validation_and_readonly_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store_dir,store,checkpoint,profile=self.setup_store(root)
            actual,target=live.stage_checkpoint(store,checkpoint.checkpoint_id,profile)
            self.assertEqual(actual,checkpoint);self.assertEqual(live.live.sha(target),checkpoint.sha256)
            self.assertEqual(live.verify_origin(store_dir,checkpoint,profile),Decimal('10.250'))
            with self.assertRaisesRegex(ValueError,'not empty'):
                live.stage_checkpoint(store,checkpoint.checkpoint_id,profile)
            with patch.object(live.snapshot,'command_for',return_value=['bwrap','--bind','case','case','--die-with-parent','--','X4']):
                cmd=live.readonly_save_command(root,root,[],root,':0',root,'u',1,target)
            self.assertLess(cmd.index('--ro-bind'),cmd.index('--die-with-parent'))
            self.assertEqual(cmd[cmd.index('--ro-bind')+1:cmd.index('--ro-bind')+3],[str(target),str(target)])

    def test_rejects_wrong_checkpoint_tampering_and_content_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store_dir,store,checkpoint,profile=self.setup_store(root)
            with self.assertRaisesRegex(ValueError,'not CURRENT'):
                live.stage_checkpoint(store,'checkpoint-'+'0'*32,profile)
            (profile/'content.xml').write_text('<content different="1"/>')
            with self.assertRaisesRegex(ValueError,'extension lists'):
                live.verify_origin(store_dir,checkpoint,profile)
            checkpoint.path.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                live.stage_checkpoint(store,checkpoint.checkpoint_id,profile)

    def test_rejects_incomplete_source_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_dir,store,checkpoint,profile=self.setup_store(Path(tmp))
            path=store_dir.parent/'result.json';record=json.loads(path.read_text())
            record['owned_processes_remaining']=[123];path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'completed checkpoint'):
                live.verify_origin(store_dir,checkpoint,profile)

    def test_verified_second_cycle_is_accepted_and_bound_to_source_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);origin, checkpoints, profile=self.setup_cycles(root)
            store_dir=origin/'checkpoints/cycle-2'
            checkpoint,target=live.stage_checkpoint(CheckpointStore(store_dir),checkpoints[1].checkpoint_id,profile)
            self.assertEqual(live.verify_origin(store_dir,checkpoint,profile),Decimal('20'))
            self.assertEqual(live.live.sha(target),checkpoint.sha256)
            with self.assertRaisesRegex(ValueError,'unsupported source'):
                live.verify_origin(origin/'checkpoints/cycle-1',checkpoints[0],profile)

    def test_cycle_origin_rejects_mismatched_evidence_and_run_identity(self):
        for index in (0, 1):
            for key,value in (('checkpoint_id','checkpoint-'+'0'*32),('sha256','0'*64),
                              ('size',999),('game_time','999'),('file_verified',False),('cycle',True)):
                with self.subTest(index=index,key=key), tempfile.TemporaryDirectory() as tmp:
                    origin, checkpoints, profile=self.setup_cycles(Path(tmp))
                    result_path=origin/'result.json';record=json.loads(result_path.read_text())
                    record['cycles'][index][key]=value;result_path.write_text(json.dumps(record))
                    with self.assertRaises(ValueError):
                        live.verify_origin(origin/'checkpoints/cycle-2',checkpoints[1],profile)
        with tempfile.TemporaryDirectory() as tmp:
            origin, checkpoints, profile=self.setup_cycles(Path(tmp))
            config=origin/'case/extensions/x4_lan_lab/ui/config.lua'
            config.write_text('authority_cycle_id="'+'b'*32+'"')
            with self.assertRaises(ValueError):
                live.verify_origin(origin/'checkpoints/cycle-2',checkpoints[1],profile)

    def test_cycle_origin_rejects_missing_prior_cycle_incomplete_log_and_content_change(self):
        for mutation in ('first_missing','log_missing','content','not_completed'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                origin, checkpoints, profile=self.setup_cycles(Path(tmp))
                if mutation=='first_missing': shutil.rmtree(origin/'checkpoints/cycle-1')
                elif mutation=='log_missing': (origin/'case/home/.config/EgoSoft/X4/45841/engine-output.log').unlink()
                elif mutation=='content': (profile/'content.xml').write_text('<different/>')
                else:
                    path=origin/'result.json';record=json.loads(path.read_text());record['success']=False
                    path.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    live.verify_origin(origin/'checkpoints/cycle-2',checkpoints[1],profile)

    def test_probe_overlay_has_no_autostart_or_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';lab=case/'extensions/x4_lan_lab'
            for name in ('ui','md'): (lab/name).mkdir(parents=True)
            (lab/'ui/config.lua').write_text('old');(lab/'ui/native_gate_snapshot.lua').write_text('old')
            (lab/'md/native_gate_battle.xml').write_text('old')
            profile=case/'home/.config/EgoSoft/X4/45841';profile.mkdir(parents=True)
            live.install_probe(case,profile)
            ui=(lab/'ui.xml').read_text()
            self.assertLess(ui.index('config.lua'),ui.index('authority_load_probe.lua'))
            self.assertNotIn('autostart',ui);self.assertNotIn('snapshot',ui)
            self.assertFalse((lab/'md/native_gate_battle.xml').exists())
            self.assertNotIn(str(profile),(lab/'ui/config.lua').read_text())

    def test_ordered_receipts_require_advancing_finite_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log';watch=live.LoadWatch(path)
            path.write_bytes(b'[X4LAN] AUTH_LOAD ARMED\n[X4LAN] AUTH_LOAD REQUEST\n[X4LAN] AUTH_LOAD READY time=3.0\n')
            self.assertTrue(watch.poll());self.assertEqual(watch.stage,3)
            with path.open('ab') as f:f.write(b'[X4LAN] AUTH_LOAD ADVANCED time=3.5\n')
            self.assertTrue(watch.poll());self.assertEqual(watch.stage,4)
            with path.open('ab') as f:f.write(b'[X4LAN] AUTH_LOAD READY time=4\n')
            with self.assertRaises(ValueError):watch.poll()
            for rows in (b'READY time=3',b'ARMED\n[X4LAN] AUTH_LOAD REQUEST\n[X4LAN] AUTH_LOAD READY time=nan',
                         b'ARMED\n[X4LAN] AUTH_LOAD REQUEST\n[X4LAN] AUTH_LOAD READY time=3\n[X4LAN] AUTH_LOAD ADVANCED time=3'):
                path.write_bytes(b'[X4LAN] AUTH_LOAD '+rows+b'\n')
                with self.assertRaises(ValueError):live.LoadWatch(path).poll()

    def test_loaded_time_rejects_regression_and_allows_rounding_and_elapsed_time(self):
        live.verify_loaded_time(Decimal('10.250'),10.249)
        live.verify_loaded_time(Decimal('10.250'),15.0)
        for saved,ready in ((Decimal('10.250'),10.2489), (Decimal('NaN'),3.0),
                            (Decimal('3'),float('nan')), (Decimal('3'),float('inf'))):
            with self.subTest(saved=saved,ready=ready), self.assertRaises(ValueError):
                live.verify_loaded_time(saved,ready)

    @unittest.skipUnless(shutil.which('luajit'),'requires LuaJIT')
    def test_lua_load_then_rebuilt_ui_observes_time(self):
        script=r'''
local menu=true;local valid=false;local paused=true;local tm=3;local logs={};local update;local loaded=0;local unpaused=0
X4LAN_CONFIG={authority_load_probe=true,test_profile='45841',authority_load_save_path='/private/45841/save'}
package.loaded.ffi={NULL={},cdef=function() end,string=function(s)return s end,C={
 IsStartmenu=function()return menu end,IsPlayerValid=function()return valid end,IsGamePaused=function()return paused end,
 IsSaveListLoadingComplete=function()return true end,ReloadSaveList=function()end,
 GetSaveFolderPath=function()return '/private/45841/save' end,GetCurrentGameTime=function()return tm end}}
DebugError=function(s) logs[#logs+1]=s end;SetScript=function(_,f) update=f end
GetSaveList=function()return {{filename='save_009'}}end
LoadGame=function(slot)assert(slot=='save_009');loaded=loaded+1 end
Unpause=function()unpaused=unpaused+1;paused=false end
assert(loadfile('tools/dev/authority_load_probe.lua'))();update();update();assert(loaded==1)
menu=false;valid=true;assert(loadfile('tools/dev/authority_load_probe.lua'))();update();assert(unpaused==1)
update();assert(#logs==3);tm=3.1;update();assert(#logs==4 and logs[4]:find('ADVANCED',1,true))
'''
        result=subprocess.run(['luajit','-'],input=script,text=True,cwd=ROOT,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
