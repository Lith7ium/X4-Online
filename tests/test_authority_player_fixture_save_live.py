"""Offline checks for the private fixture-save harness; no game is started."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tempfile
import unittest
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT/'tools/dev'))
import authority_player_fixture_save_live as live


class FixtureSaveLiveTests(unittest.TestCase):
    def setUp(self):
        self.ticket = dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
            checkpoint_id=live.base.archive.CHECKPOINT_ID,sha256=live.base.archive.SHA256,
            attempt_id='b'*32,slot='save_008')
        fields = '|'.join(str(self.ticket[k]) for k in live.base.load.FIELDS)
        tag = live.base.load.TAG.decode()
        self.baseline = [tag+'load_requested|'+fields,
            '[X4LAN] AUTH_MARKER load INSPECTED '+live.base.archive.MARKER,
            '[X4LAN] AUTH_SECTOR_READ DONE slot=2 pilot=present order=Patrol state=started game=3 x=1 y=2 z=3',
            tag+'pause_observed|'+fields]

    def raw(self, lines): return ('\n'.join(lines)+'\n').encode()

    def test_only_ordered_post_pause_creation_is_accepted(self):
        preflight,created = live.TAG+'PREFLIGHT',live.TAG+'CREATED'
        self.assertIsNone(live.validate(self.raw(self.baseline+[preflight]),self.ticket,2,partial=True))
        result=live.validate(self.raw(self.baseline+[preflight,created]),self.ticket,2)
        self.assertTrue(result['fixture_created_receipt'])
        self.assertFalse(result['fixture_registry_enrollment_proven'])
        self.assertFalse(result['multiplayer_proven'])
        for rows in (self.baseline+[created,preflight],self.baseline+[preflight,created,created],
                     self.baseline[:3]+[preflight]+self.baseline[3:]+[created],
                     self.baseline+[preflight,created,live.TAG+'ERROR']):
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                live.validate(self.raw(rows),self.ticket,2)

    def test_install_protects_both_new_modules_and_keeps_one_update_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            case=Path(temporary)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab'
            ui,md=lab/'ui',lab/'md';ui.mkdir(parents=True);md.mkdir();(lab/'native').mkdir()
            (profile/'save').mkdir(parents=True)
            for path in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
                         lab/'content.xml',profile/'content.xml',profile/'config.xml'):
                path.write_text('test')
            ticket=dict(self.ticket,slot='save_009')
            protected=live.install(case,profile,ticket,2,port=12345,lease='c'*32,world_epoch='d'*32,nonce='e'*32)
            self.assertEqual(ticket['slot'],'save_008')
            self.assertIn(ui/'authority_player_fixture_save_probe.lua',protected)
            self.assertIn(ui/'authority_world_bridge_probe.lua',protected)
            self.assertIn(lab/'native/x4lan_net.so',protected)
            owner=(ui/'authority_download_load_probe.lua').read_text()
            bridge=(ui/'authority_world_bridge_probe.lua').read_text()
            self.assertEqual(owner.count("SetScript('onUpdate'"),1)
            self.assertNotIn("SetScript('onUpdate'",bridge)
            self.assertIn('X4LAN_PLAYER_FIXTURE_SAVE_TICK();X4LAN_PLAYER_WORLD_BRIDGE_TICK()',owner)
            self.assertIn('X4AuthorityPlayerFixtureMarker',bridge)
            self.assertNotIn('X4AuthorityCheckpointMarker',bridge)
            self.assertIn('X4LAN_PLAYER_FIXTURE_SAVE_READY()',bridge)

    def test_opted_in_install_uses_the_pinned_historical_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            case=Path(temporary)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab'
            ui,md=lab/'ui',lab/'md';ui.mkdir(parents=True);md.mkdir();(lab/'native').mkdir()
            (profile/'save').mkdir(parents=True)
            for path in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
                         lab/'content.xml',profile/'content.xml',profile/'config.xml'):
                path.write_text('test')
            ticket=dict(self.ticket,slot='save_009')
            historical=live.historical_registry()
            protected=live.install(case,profile,ticket,2,port=12345,lease='c'*32,world_epoch='d'*32,
                                   nonce='e'*32,registry_script=historical)
            installed=md/'authority_ship_registry.xml'
            self.assertIn(installed,protected)
            self.assertEqual(installed.read_bytes(),historical.read_bytes())
            self.assertNotEqual(installed.read_bytes(),(ROOT/'tools/dev/authority_ship_registry.xml').read_bytes())

    def test_historical_registry_must_match_its_pinned_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            modified=Path(temporary)/'authority_ship_registry.xml'
            modified.write_bytes(live.HISTORICAL_REGISTRY.read_bytes()+b'<!-- changed -->')
            with patch.object(live,'HISTORICAL_REGISTRY',modified):
                with self.assertRaisesRegex(ValueError,'pinned fixture'):
                    live.historical_registry()
                ticket=dict(self.ticket,slot='save_009')
                with self.assertRaisesRegex(ValueError,'pinned fixture'):
                    live.install(Path(temporary),Path(temporary),ticket,2,port=12345,lease='c'*32,
                                 world_epoch='d'*32,nonce='e'*32,registry_script=modified)
                self.assertEqual(ticket['slot'],'save_009')

    def test_archive_registry_still_has_to_match_selected_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);store=root/'test/checkpoints';store.mkdir(parents=True)
            origin=store.parent/'server/case'
            archived_md=origin/'extensions/x4_lan_lab/md';archived_md.mkdir(parents=True)
            original_content=origin/'home/.config/EgoSoft/X4/45841/content.xml'
            original_content.parent.mkdir(parents=True);original_content.write_text('same content')
            profile=root/'profile';profile.mkdir();(profile/'content.xml').write_text('same content')
            for name in live.base.MD:
                source=live.HISTORICAL_REGISTRY if name=='authority_ship_registry.xml' else ROOT/'tools/dev'/name
                shutil.copyfile(source,archived_md/name)
            with self.assertRaisesRegex(ValueError,'saved-state scripts differ'):
                live.base.check_origin_scripts(store,profile)
            live.base.check_origin_scripts(store,profile,registry_script=live.historical_registry())
            (archived_md/'authority_ship_registry.xml').write_text('different registry')
            with self.assertRaisesRegex(ValueError,'saved-state scripts differ'):
                live.base.check_origin_scripts(store,profile,registry_script=live.historical_registry())

    def test_supervisor_hooks_restore_on_failure_and_source_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Path(temporary)/'checkpoints';store.mkdir()
            args=SimpleNamespace(slot=2,timeout=120,store=store)
            original=(live.base.install,live.base.check_origin_scripts,live.base.check_log_bytes,
                      live.base.fault_log,live.base.observation_callback,live.base.result_finalizer,
                      live.base.base.stage_checkpoint)
            def fake_run(_):
                self.assertTrue(callable(live.base.observation_callback))
                self.assertIsNot(live.base.check_origin_scripts,original[1])
                live.base.result_finalizer({'success':False})
                raise RuntimeError('synthetic failure')
            with patch.object(live.base.base,'local_directory',return_value=store), \
                 patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':1}]), \
                 patch.object(live.base,'run',side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError,'synthetic failure'): live.run(args)
            self.assertEqual(original,(live.base.install,live.base.check_origin_scripts,live.base.check_log_bytes,live.base.fault_log,
                live.base.observation_callback,live.base.result_finalizer,live.base.base.stage_checkpoint))

    def test_lost_guard_after_save_never_publishes_or_confirms(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);store_dir=root/'source';store_dir.mkdir();out=root/'out';out.mkdir()
            profile=root/'45841';(profile/'save').mkdir(parents=True)
            game=root/'game';game.mkdir();(game/'X4').write_bytes(b'fake executable')
            args=SimpleNamespace(slot=2,timeout=120,store=store_dir)
            alive=[True]
            class FakeSocket:
                def bind(self,_): pass
                def settimeout(self,_): pass
                def getsockname(self): return ('127.0.0.1',1234)
                def recvfrom(self,_): return (('HELLO|'+'a'*32+'|'+'b'*32).encode(),('127.0.0.1',1235))
                def close(self): pass
            class FakeBridge:
                pending_marker='f'*32
                def __init__(self,**_): pass
                def pause(self): pass
                def save_fixture_experiment(self,*,enabled):
                    assert enabled
                    alive[0]=False
                    return profile/'save/save_009.xml.gz'
            checkpoint_store=Mock()
            def guard():
                if not alive[0]: raise RuntimeError('ownership lost')
                return True
            def fake_run(_):
                try:
                    return live.base.observation_callback(profile=profile,out=out,game=game,identity=(123,1),
                        deadline=time.monotonic()+30,guard=guard)
                finally:
                    result={'success':False}
                    live.base.result_finalizer(result)
                    self.assertTrue(result['save_attempted'])
                    self.assertTrue(result['checkpoint_requested'])
                    self.assertFalse(result['checkpoint_confirmed'])
            with patch.object(live.base.base,'local_directory',return_value=store_dir), \
                 patch.object(live.base.archive,'_path_fingerprints',return_value={}), \
                 patch.object(live.secrets,'token_hex',side_effect=['a'*32,'b'*32,'c'*32]), \
                 patch.object(live.socket,'socket',return_value=FakeSocket()), \
                 patch.object(live,'socket_owner',return_value=True), \
                 patch.object(live,'PlayerFixtureBridge',FakeBridge), \
                 patch.object(live,'CheckpointStore',return_value=checkpoint_store), \
                 patch.object(live.base,'stable_read',return_value=(None,None,b'clean\n')), \
                 patch.object(live.base,'run',side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError,'ownership lost'): live.run(args)
            checkpoint_store.publish.assert_not_called()
            checkpoint_store.confirm.assert_not_called()

    def test_confirmation_waits_for_successful_final_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';source.mkdir();out=root/'out';out.mkdir()
            profile=root/'45841';(profile/'save').mkdir(parents=True)
            game=root/'game';game.mkdir();(game/'X4').write_bytes(b'fake executable')
            args=SimpleNamespace(slot=2,timeout=120,store=source)
            class FakeSocket:
                def bind(self,_): pass
                def settimeout(self,_): pass
                def getsockname(self): return ('127.0.0.1',1234)
                def recvfrom(self,_): return (('HELLO|'+'a'*32+'|'+'b'*32).encode(),('127.0.0.1',1235))
                def close(self): pass
            class FakeBridge:
                pending_marker='f'*32
                def __init__(self,**_): pass
                def pause(self): pass
                def save_fixture_experiment(self,*,enabled): return profile/'save/save_009.xml.gz'
                def checkpoint_published(self,_): return True
            checkpoint=SimpleNamespace(checkpoint_id='checkpoint',sha256='digest')
            checkpoint_store=Mock();checkpoint_store.publish.return_value=checkpoint
            def fake_run(_):
                experiment=live.base.observation_callback(profile=profile,out=out,game=game,identity=(123,1),
                    deadline=time.monotonic()+30,guard=lambda:True)
                checkpoint_store.confirm.assert_not_called()
                failed={'success':False,'experiment':dict(experiment)}
                live.base.result_finalizer(failed)
                checkpoint_store.confirm.assert_not_called()
                self.assertFalse(failed['checkpoint_confirmed'])
                pointer=out/'visible-confirmed'
                def uncertain_confirm(_):
                    pointer.write_text('visible')
                    raise OSError('synthetic fsync failure')
                checkpoint_store.confirm.side_effect=uncertain_confirm
                uncertain={'success':True,'experiment':dict(experiment)}
                with self.assertRaisesRegex(OSError,'fsync'):
                    live.base.result_finalizer(uncertain)
                self.assertTrue(pointer.exists())
                self.assertTrue(uncertain['confirmation_attempted'])
                self.assertTrue(uncertain['checkpoint_confirmation_uncertain'])
                self.assertFalse(uncertain['checkpoint_confirmed'])
                checkpoint_store.confirm.reset_mock()
                checkpoint_store.confirm.side_effect=None
                passed={'success':True,'experiment':experiment}
                live.base.result_finalizer(passed)
                checkpoint_store.confirm.assert_called_once_with(checkpoint)
                self.assertTrue(passed['checkpoint_confirmed'])
                self.assertTrue(passed['confirmation_attempted'])
                self.assertFalse(passed['checkpoint_confirmation_uncertain'])
                self.assertTrue(passed['experiment']['checkpoint_confirmed'])
                return passed
            with patch.object(live.base.base,'local_directory',return_value=source), \
                 patch.object(live.base.archive,'_path_fingerprints',return_value={}), \
                 patch.object(live.secrets,'token_hex',side_effect=['a'*32,'b'*32,'c'*32]), \
                 patch.object(live.socket,'socket',return_value=FakeSocket()), \
                 patch.object(live,'socket_owner',return_value=True), \
                 patch.object(live,'PlayerFixtureBridge',FakeBridge), \
                 patch.object(live,'CheckpointStore',return_value=checkpoint_store), \
                 patch.object(live.base,'stable_read',return_value=(None,None,b'clean\n')), \
                 patch.object(live.base,'run',side_effect=fake_run):
                result=live.run(args)
            self.assertTrue(result['save_attempted'])

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'),'LuaJIT and C compiler required')
    def test_fixture_owner_with_synthetic_x4_abi(self):
        with tempfile.TemporaryDirectory() as temporary:
            library=Path(temporary)/'fake-x4.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_player_seat_fake_x4.c',
                'tests/lua/authority_player_seat_experiment_time.c','-o',str(library)],cwd=ROOT,
                check=True,capture_output=True,timeout=10)
            for scenario in ('normal','bad_preflight','timeout'):
                subprocess.run(['luajit','tests/authority_player_fixture_save_x4.lua',str(library),scenario],
                    cwd=ROOT,check=True,capture_output=True,timeout=5)


if __name__=='__main__': unittest.main()
