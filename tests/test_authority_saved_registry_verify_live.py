"""Focused offline checks for the saved four-entry registry reload."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_saved_registry_verify_live as subject
import authority_saved_registry_checkpoint_source as source


class SavedRegistryVerifyTests(unittest.TestCase):
    def test_source_requires_confirmed_new_checkpoint_and_complete_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            origin = Path(directory) / 'run'
            store = origin / 'checkpoints'; store.mkdir(parents=True)
            profile = Path(directory) / 'profile'; profile.mkdir()
            (profile / 'content.xml').write_bytes(b'content')
            original_profile = origin / 'case/home/.config/EgoSoft/X4/45841'
            original_profile.mkdir(parents=True)
            (original_profile / 'content.xml').write_bytes(b'content')
            md = origin / 'case/extensions/x4_lan_lab/md'; md.mkdir(parents=True)
            for name in source.fixture_source.SAVED_SCRIPTS:
                path = (source.fixture_source.fixture_save.historical_registry() if name == 'authority_ship_registry.xml'
                        else ROOT / 'tools/dev' / name)
                shutil.copyfile(path, md / name)
            checkpoint = SimpleNamespace(checkpoint_id='checkpoint-a', sha256='f'*64, marker='a'*32)
            result = {'success': True, 'checkpoint_confirmed': True, 'confirmation_attempted': True,
                'checkpoint_confirmation_uncertain': False, 'saved_registry_mapping_verified': True,
                'owned_processes_remaining': [], 'experiment': {'checkpoint_confirmed': True,
                'saved_fixture_registry_mapping_checked': True, 'checkpoint_id': checkpoint.checkpoint_id,
                'sha256': checkpoint.sha256}}
            result_path = origin / 'registry-save-result.json'
            result_path.write_text(json.dumps(result))
            fake_store = SimpleNamespace(latest_marked_confirmed=lambda: checkpoint)
            with patch.object(source, 'CheckpointStore', return_value=fake_store), \
                 patch.object(source.fixture_evidence, 'verify', return_value={
                    'saved_slots_checked': 2, 'saved_owner_class_sector_checked': True,
                    'saved_registry_slot_mapping_checked': True}) as verify:
                scripts = source.verify(store, checkpoint, profile)
                self.assertEqual(set(scripts), set(source.fixture_source.SAVED_SCRIPTS))
                self.assertEqual(verify.call_args.kwargs, {'registry_count': 4, 'fixture_indices': (3, 4)})
                result['checkpoint_confirmation_uncertain'] = True
                result_path.write_text(json.dumps(result))
                with self.assertRaisesRegex(ValueError, 'not cleanly confirmed'):
                    source.verify(store, checkpoint, profile)

    def test_installer_keeps_saved_scripts_and_single_update_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / 'case'; profile = case / 'profile'
            lab = case / 'extensions/x4_lan_lab'; ui, md = lab / 'ui', lab / 'md'
            ui.mkdir(parents=True); md.mkdir(); (profile / 'save').mkdir(parents=True)
            for path in (ui / 'native_gate_snapshot.lua', md / 'native_gate_battle.xml', ui / 'config.lua'):
                path.write_text('test')
            scripts = {name: ('preserved:' + name).encode() for name in source.fixture_source.SAVED_SCRIPTS}
            config, protected = subject.install(case, profile, scripts, nonce='a'*32, timeout=60,
                                                 original_install=subject.recovery.install_probe)
            for name, contents in scripts.items():
                self.assertEqual((md / name).read_bytes(), contents)
            self.assertIn(md / 'authority_saved_registry_verify.xml', protected)
            self.assertIn(ui / 'authority_saved_registry_verify_owner.lua', protected)
            self.assertEqual((ui / 'authority_recovery_probe.lua').read_text().count("SetScript('onUpdate'"), 1)
            self.assertIn('authority_saved_registry_verify=true', config.read_text())
            marker = (ui / 'authority_checkpoint_marker_probe.lua').read_text()
            self.assertNotIn('X4AuthorityCheckpointMarker', marker)
            self.assertIn('X4AuthorityPlayerFixtureMarker', marker)
            root = ET.parse(md / 'authority_saved_registry_verify.xml').getroot()
            text = ET.tostring(root, encoding='unicode')
            self.assertNotIn('Enroll', text); self.assertNotIn('Initialize', text)
            self.assertNotIn('player.ship', text); self.assertNotIn('player.container', text)

    def test_watch_requires_single_ordered_result_and_rejects_faults(self):
        marker = 'a'*32
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'engine.log'
            rows = ['[X4LAN] AUTH_RECOVERY REQUEST', '[X4LAN] AUTH_MARKER load INSPECTED ' + marker,
                    '[X4LAN] AUTH_RECOVERY PAUSED', subject.TAG + 'MATCHED 4 3 4']
            path.write_text('\n'.join(rows) + '\n')
            watch = subject.RegistryVerifyWatch(path, marker)
            self.assertTrue(watch.poll())
            with path.open('a') as stream:
                stream.write(subject.TAG + 'ERROR\n')
            with self.assertRaises(ValueError):
                watch.poll()

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'), 'LuaJIT and C compiler required')
    def test_owner_checks_correlation_and_final_guard_before_success(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / 'fake.so'
            subprocess.run(['cc', '-shared', '-fPIC', 'tests/lua/authority_player_control_fake_x4.c',
                            '-o', str(library)], cwd=ROOT, check=True, capture_output=True)
            for scenario in ('early', 'bad_nonce', 'timeout', 'success'):
                subprocess.run(['luajit', 'tests/authority_saved_registry_verify_owner.lua', str(library), scenario],
                               cwd=ROOT, check=True, capture_output=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
