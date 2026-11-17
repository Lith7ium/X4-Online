"""Offline checks for a saved-fixture reload and seat probe; no X4 start."""
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev'), str(ROOT / 'tests')]
from authority.checkpoints import CheckpointStore
import authority_fixture_checkpoint_source as fixture_source
import authority_saved_player_control_live as live
import test_authority_player_sector_fixture as fixture_test


class SavedPlayerControlTests(unittest.TestCase):
    def test_md_selects_saved_slots_without_creating_a_ship(self):
        root = ET.parse(ROOT / 'tools/dev/authority_saved_player_control.xml').getroot()
        self.assertEqual(root.get('name'), 'X4AuthoritySavedPlayerControl')
        self.assertEqual(root.findall('.//create_ship'), [])
        self.assertEqual(len(root.findall('.//teleport_player')), 1)
        xml = ET.tostring(root, encoding='unicode')
        for name in ('$ship1', '$ship2', '$sector1', '$sector2'):
            self.assertIn('md.X4AuthorityPlayerSectorFixture.State.' + name, xml)

    def test_control_receipts_require_ordered_pause_and_action(self):
        baseline = ['[X4LAN] AUTH_RECOVERY REQUEST', '[X4LAN] AUTH_MARKER load INSPECTED ' + 'a' * 32,
                    '[X4LAN] AUTH_RECOVERY PAUSED']
        controls = [live.CONTROL_TAG + value for value in live.EXPECTED_CONTROL]
        rows = baseline + controls[:5] + [live.ACTION_TAG + 'ACTION_BEGIN',live.ACTION_TAG + 'ACTION_RETURNED'] + controls[5:]
        raw = lambda lines: ('\n'.join(lines) + '\n').encode()
        self.assertTrue(live.check_control_log(raw(rows), partial=False))
        self.assertFalse(live.check_control_log(raw(baseline + controls[:2]), partial=True))
        self.assertFalse(live.check_control_log(raw(rows[:-1]), partial=True))
        with self.assertRaisesRegex(ValueError,'incomplete'):
            live.check_control_log(raw(rows[:-1]), partial=False)
        for invalid in (rows + [controls[-1]], baseline + controls, baseline[:2] + controls[:1] + baseline[2:] + controls[1:],
                        rows + ['Error while parsing expression: bad']):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                live.check_control_log(raw(invalid), partial=False)

    def test_watcher_waits_for_log_and_requires_complete_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'engine-output.log';marker='a'*32
            watch=live.SavedControlWatch(path,marker)
            self.assertFalse(watch.poll())
            path.write_text('[X4LAN] AUTH_RECOVERY REQUEST\n[X4LAN] AUTH_MARKER load INSPECTED '+marker+
                            '\n[X4LAN] AUTH_RECOVERY PAUSED\n')
            self.assertFalse(watch.poll())
            controls=[live.CONTROL_TAG+value for value in live.EXPECTED_CONTROL]
            rows=controls[:5]+[live.ACTION_TAG+'ACTION_BEGIN',live.ACTION_TAG+'ACTION_RETURNED']+controls[5:]
            with path.open('a') as stream:
                stream.write('\n'.join(rows)+'\n')
            self.assertTrue(watch.poll())
            with path.open('a') as stream:
                stream.write(live.CONTROL_TAG+'DONE\n')
            with self.assertRaises(ValueError):
                watch.poll()

    def test_private_installer_preserves_saved_scripts_and_one_update_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            case=Path(temporary)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab'
            ui,md=lab/'ui',lab/'md';ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
            for path in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua'):
                path.write_text('test')
            scripts={}
            for name in fixture_source.SAVED_SCRIPTS:
                path=(fixture_source.fixture_save.historical_registry() if name=='authority_ship_registry.xml'
                      else ROOT/'tools/dev'/name)
                scripts[name]=path.read_bytes()
            config,protected=live.install(case,profile,scripts,slot=2,nonce='b'*32,timeout=90,
                                          original_install=live.recovery.install_probe)
            for name,contents in scripts.items():
                self.assertEqual((md/name).read_bytes(),contents)
                self.assertIn(md/name,protected)
            self.assertIn('authority_fixture_slot=2',config.read_text())
            owner=(ui/'authority_recovery_probe.lua').read_text()
            self.assertEqual(owner.count("SetScript('onUpdate'"),1)
            self.assertIn('X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()',owner)
            self.assertIn('X4AuthorityPlayerFixtureMarker',(ui/'authority_checkpoint_marker_probe.lua').read_text())
            self.assertIn('slot=o.slot',(ui/'authority_player_control_once.lua').read_text())

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'), 'LuaJIT and C compiler required')
    def test_saved_player_owner_against_synthetic_abi(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary=Path(temporary);library=temporary/'fake-x4.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_player_control_fake_x4.c','-o',str(library)],
                           cwd=ROOT,check=True,capture_output=True,timeout=10)
            control=temporary/'control.lua'
            control.write_text(live.replace_once((ROOT/'tools/dev/authority_player_control_once.lua').read_text(),
                'local args={epoch=o.epoch,request_id=o.nonce}',
                'local args={epoch=o.epoch,request_id=o.nonce,slot=o.slot}'))
            for scenario in ('normal','bad_nonce','rogue','post_done_fault'):
                subprocess.run(['luajit','tests/authority_saved_player_control_x4.lua',str(library),str(control),scenario],
                               cwd=ROOT,check=True,capture_output=True,timeout=5)

    def test_fixture_source_rejects_failed_result_and_changed_saved_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);origin=root/'fixture';store_path=origin/'checkpoints';store_path.mkdir(parents=True)
            profile=root/'profile';profile.mkdir();(profile/'content.xml').write_text('same')
            original_profile=origin/'case/home/.config/EgoSoft/X4/45841';original_profile.mkdir(parents=True)
            (original_profile/'content.xml').write_text('same')
            md=origin/'case/extensions/x4_lan_lab/md';md.mkdir(parents=True)
            for name in fixture_source.SAVED_SCRIPTS:
                source=(fixture_source.fixture_save.historical_registry() if name=='authority_ship_registry.xml'
                        else ROOT/'tools/dev'/name)
                shutil.copyfile(source,md/name)
            marker=fixture_test.MARKER
            epoch=fixture_source.fixture_save.base.archive.REGISTRY_EPOCH
            xml=fixture_test.document().replace(fixture_test.EPOCH,epoch)
            save=root/'fixture.gz';save.write_bytes(gzip.compress(xml.encode()))
            store=CheckpointStore(store_path);checkpoint=store.publish(save,marker=marker);store.confirm(checkpoint)
            result={'success':True,'checkpoint_confirmed':True,'confirmation_attempted':True,
                    'checkpoint_confirmation_uncertain':False,'owned_processes_remaining':[],
                    'experiment':{'checkpoint_confirmed':True,'saved_fixture_references_checked':True,
                                  'checkpoint_id':checkpoint.checkpoint_id,'sha256':checkpoint.sha256}}
            result_file=origin/'result.json';result_file.write_text(json.dumps(result))
            self.assertEqual(set(fixture_source.verify(store_path,checkpoint,profile)),set(fixture_source.SAVED_SCRIPTS))
            result['success']=False;result_file.write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'cleanly confirmed'):
                fixture_source.verify(store_path,checkpoint,profile)
            result['success']=True;result_file.write_text(json.dumps(result))
            (md/'authority_player_sector_fixture.xml').write_text('changed')
            with self.assertRaisesRegex(ValueError,'saved-state script differs'):
                fixture_source.verify(store_path,checkpoint,profile)

    def test_recovery_hooks_are_restored_after_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Path(temporary)/'checkpoints';store.mkdir()
            args=SimpleNamespace(slot=2,timeout=120,store=store)
            original=(live.recovery.stage_confirmed_recovery,live.recovery.verify_source,
                live.recovery.install_probe,live.recovery.RecoveryWatch,
                live.recovery.extra_protected_files,live.recovery.result_finalizer)
            def fake_run(_):
                self.assertIs(live.recovery.RecoveryWatch,live.SavedControlWatch)
                result={'success':False,'error':'original failure'}
                live.recovery.result_finalizer(result)
                self.assertEqual(result['error'],'original failure')
                raise RuntimeError('injected stop')
            with patch.object(live.recovery.base,'local_directory',return_value=store), \
                 patch.object(live.recovery,'run',side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError,'injected stop'):
                    live.run(args)
            self.assertEqual(original,(live.recovery.stage_confirmed_recovery,live.recovery.verify_source,
                live.recovery.install_probe,live.recovery.RecoveryWatch,
                live.recovery.extra_protected_files,live.recovery.result_finalizer))


if __name__ == '__main__':
    unittest.main()
