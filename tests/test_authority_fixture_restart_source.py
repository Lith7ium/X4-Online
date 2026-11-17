"""Offline provenance checks for restarting a fixture supervisor output."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_recovered_loopback_server as server
import authority_saved_registry_checkpoint_source as source


class FixtureRestartSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.origin = root / 'server'
        self.store = self.origin / 'checkpoints'
        self.store.mkdir(parents=True)
        (self.store / 'CURRENT').write_bytes(b'confirmed')
        (self.store / 'CONFIRMED').write_bytes(b'confirmed')
        self.profile = root / 'profile'
        self.profile.mkdir()
        (self.profile / 'content.xml').write_bytes(b'content')
        old_profile = self.origin / 'case/home/.config/EgoSoft/X4/45841'
        old_profile.mkdir(parents=True)
        (old_profile / 'content.xml').write_bytes(b'content')
        self.md = self.origin / 'case/extensions/x4_lan_lab/md'
        self.md.mkdir(parents=True)
        for name in source.fixture_source.SAVED_SCRIPTS:
            original = (source.fixture_source.fixture_save.historical_registry()
                        if name == 'authority_ship_registry.xml' else ROOT / 'tools/dev' / name)
            shutil.copyfile(original, self.md / name)
        self.checkpoint = SimpleNamespace(checkpoint_id='checkpoint-a', sha256='f'*64, marker='a'*32)
        self.result = {'supervisor_version': 1, 'fixture_overlap': True, 'fixture_registry_count': 4,
                       'success': True, 'final_world_state': 'paused', 'owned_processes_remaining': [],
                       'final_checkpoint_id': self.checkpoint.checkpoint_id,
                       'final_checkpoint_sha256': self.checkpoint.sha256}
        self.result_path = self.origin / 'result.json'
        self.write_result()
        self.fake_store = SimpleNamespace(directory=self.store, latest_marked_confirmed=lambda: self.checkpoint)
        self.store_patch = patch.object(source, 'CheckpointStore', return_value=self.fake_store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.mapping_patch = patch.object(source.fixture_evidence, 'verify', return_value={
            'saved_slots_checked': 2, 'saved_owner_class_sector_checked': True,
            'saved_registry_slot_mapping_checked': True})
        self.mapping = self.mapping_patch.start()
        self.addCleanup(self.mapping_patch.stop)

    def write_result(self):
        self.result_path.write_text(json.dumps(self.result))

    def verify(self):
        return server.verify_fixture_source(self.fake_store, self.checkpoint, self.profile)

    def test_recovered_server_source_reuses_mapping_without_original_sector_restriction(self):
        scripts, path, evidence = self.verify()
        self.assertEqual(set(scripts), set(source.fixture_source.SAVED_SCRIPTS))
        self.assertEqual(path, self.result_path)
        self.assertEqual(evidence, self.result_path.read_bytes())
        self.assertEqual(self.mapping.call_args.kwargs,
                         {'registry_count': 4, 'fixture_indices': (3, 4), 'require_original_sector': False})

    def test_rejects_unclean_or_wrong_result_and_unconfirmed_current(self):
        invalid = {'success': False, 'final_world_state': 'running', 'owned_processes_remaining': [123],
                   'final_checkpoint_id': 'other', 'final_checkpoint_sha256': 'e'*64,
                   'fixture_overlap': False, 'fixture_registry_count': 2, 'supervisor_version': True,
                   'cleanup_errors': []}
        for key, value in invalid.items():
            with self.subTest(field=key):
                original = self.result.get(key)
                self.result[key] = value
                self.write_result()
                with self.assertRaises(ValueError):
                    self.verify()
                if key == 'cleanup_errors':
                    del self.result[key]
                else:
                    self.result[key] = original
        self.write_result()
        (self.store / 'CURRENT').write_bytes(b'unconfirmed')
        with self.assertRaisesRegex(ValueError, 'current checkpoint is not confirmed'):
            self.verify()

    def test_rejects_bad_mapping_changed_script_and_ambiguous_json(self):
        self.mapping.return_value['saved_registry_slot_mapping_checked'] = False
        with self.assertRaisesRegex(ValueError, 'mapping not verified'):
            self.verify()
        self.mapping.return_value['saved_registry_slot_mapping_checked'] = True
        (self.md / 'authority_ship_registry.xml').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'script differs'):
            self.verify()
        self.result_path.write_text('{"success":true,"success":true}')
        with self.assertRaises(ValueError):
            self.verify()

    def test_rechecks_current_after_saved_mapping_verification(self):
        verified_mapping = self.mapping.return_value
        def change_current(*_args, **_kwargs):
            (self.store / 'CURRENT').write_bytes(b'unconfirmed')
            return verified_mapping
        self.mapping.side_effect = change_current
        with self.assertRaisesRegex(ValueError, 'current checkpoint is not confirmed'):
            self.verify()

    def test_invalid_original_result_does_not_fall_back_to_server_result(self):
        (self.origin / 'registry-save-result.json').write_text('{}')
        with patch.object(source, 'verify_recovered') as recovered:
            with self.assertRaisesRegex(ValueError, 'not cleanly confirmed'):
                self.verify()
            recovered.assert_not_called()


if __name__ == '__main__':
    unittest.main()
