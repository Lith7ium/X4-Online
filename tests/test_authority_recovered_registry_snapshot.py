"""Offline source and lifetime checks for opt-in format-3 server recovery."""
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('registry_snapshot_server',
    ROOT / 'tools/dev/authority_recovered_loopback_server.py')
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)
import authority_recovered_registry_snapshot as snapshots


class ConfirmedSnapshotSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        origin = Path(temporary.name) / 'prior'
        self.md = origin / 'case/extensions/x4_lan_lab/md'
        self.md.mkdir(parents=True)
        for name, path in (
            ('authority_checkpoint_marker.xml', ROOT / 'src/authority/md/checkpoint_marker.xml'),
            ('authority_identity_fixture.xml', ROOT / 'tools/dev/authority_identity_fixture.xml'),
            ('authority_ship_registry.xml', ROOT / 'tools/dev/authority_ship_registry.xml'),
            ('authority_registry_availability_snapshot.xml',
             ROOT / 'tools/dev/authority_registry_availability_snapshot.xml'),
        ):
            shutil.copyfile(path, self.md / name)
        content = origin / 'case/home/.config/EgoSoft/X4/45841/content.xml'
        content.parent.mkdir(parents=True)
        content.write_bytes(b'<content/>')
        self.profile = Path(temporary.name) / 'profile'
        self.profile.mkdir()
        (self.profile / 'content.xml').write_bytes(content.read_bytes())
        checkpoint_dir = origin / 'checkpoints'
        checkpoint_dir.mkdir()
        for name in ('CURRENT', 'CONFIRMED'):
            (checkpoint_dir / name).write_text('same pointer\n')
        self.checkpoint = SimpleNamespace(checkpoint_id='checkpoint-id', sha256='f' * 64,
                                          marker='b' * 32)
        self.store = SimpleNamespace(directory=checkpoint_dir,
                                     latest_marked_confirmed=lambda: self.checkpoint)
        self.evidence = {'format': 3, 'source_registry_checked': True, 'epoch': 'a' * 32,
                         'run_id': self.checkpoint.marker, 'issued_count': 3,
                         'availability_bits': '110', 'operational_bits': '100',
                         'availability_sha256': '1' * 64, 'operational_sha256': '2' * 64,
                         'mapping_sha256': '3' * 64}
        self.result = {'supervisor_version': 1, 'success': True, 'final_world_state': 'paused',
                       'owned_processes_remaining': [], 'final_checkpoint_id': 'checkpoint-id',
                       'final_checkpoint_sha256': 'f' * 64,
                       'registry_snapshot': {'initial_inspect_verified': True,
                           'final_receipt': snapshots.receipt(self.checkpoint, self.evidence)}}
        self.result_path = origin / 'result.json'
        self.write_result()

    def write_result(self):
        self.result_path.write_text(json.dumps(self.result))

    def verify(self):
        with patch('authority.registry_availability_evidence.verify_join_snapshot',
                   return_value=self.evidence):
            return server.verify_previous_source(self.store, self.checkpoint, self.profile,
                                                 require_registry_snapshot=True)

    def test_exact_confirmed_format3_source_is_accepted(self):
        self.assertEqual(self.verify(),
                         ((ROOT / 'tools/dev/authority_identity_fixture.xml').read_bytes(), self.evidence))

    def test_standalone_or_changed_source_is_refused(self):
        cases = (
            lambda: (self.md / 'authority_registry_availability_snapshot.xml').unlink(),
            lambda: (self.md / 'authority_registry_availability_snapshot.xml').write_text('changed'),
            lambda: (self.md / 'unexpected.xml').write_text('<mdscript/>'),
            lambda: (self.store.directory / 'CURRENT').write_text('other pointer\n'),
            lambda: setattr(self, 'checkpoint', SimpleNamespace(checkpoint_id='other',
                                                                  sha256='f' * 64, marker='b' * 32)),
            lambda: self.result.update(success=False),
            lambda: self.result.pop('registry_snapshot'),
            lambda: self.result['registry_snapshot']['final_receipt'].update(mapping_sha256='0' * 64),
            lambda: self.result_path.unlink(),
        )
        for change in cases:
            with self.subTest(change=change.__code__.co_firstlineno):
                self.setUp()
                change()
                self.write_result() if self.result_path.exists() else None
                with self.assertRaises((ValueError, OSError)):
                    self.verify()


class SnapshotModeTests(unittest.TestCase):
    def test_opt_in_rejects_other_diagnostic_owners(self):
        self.assertFalse(snapshots.validate_mode(SimpleNamespace()))
        self.assertTrue(snapshots.validate_mode(SimpleNamespace(
            require_registry_snapshot=True, diagnostic_guard_cache_ms=0)))
        for name, value in (('registry_status', True), ('registry_enroll', True),
                            ('diagnostic_client', True), ('fixture_overlap', True),
                            ('diagnostic_guard_cache_ms', 250)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                snapshots.validate_mode(SimpleNamespace(require_registry_snapshot=True,
                                                        **{name: value}))

    def test_epoch_count_and_missing_lifetime_are_stable(self):
        baseline = {'epoch': 'a' * 32, 'issued_count': 4,
                    'run_id': 'b' * 32, 'availability_bits': '1101',
                    'mapping_sha256': '1' * 64}
        next_save = {**baseline, 'run_id': 'c' * 32,
                     'availability_bits': '1001', 'mapping_sha256': '2' * 64}
        snapshots.verify_transition(baseline, next_save)
        for change in ({'epoch': 'd' * 32}, {'issued_count': 5},
                       {'run_id': baseline['run_id']}, {'availability_bits': '1111'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                snapshots.verify_transition(baseline, {**next_save, **change})

    def test_state_keeps_only_latest_verified_receipt(self):
        source = SimpleNamespace(checkpoint_id='source', sha256='1' * 64, marker='a' * 32)
        saved = SimpleNamespace(checkpoint_id='saved', sha256='2' * 64, marker='b' * 32)
        first = {'format': 3, 'source_registry_checked': True, 'run_id': source.marker,
                 'epoch': 'c' * 32, 'issued_count': 3, 'availability_bits': '110',
                 'availability_sha256': '3' * 64, 'operational_sha256': '4' * 64,
                 'mapping_sha256': '5' * 64}
        second = {**first, 'run_id': saved.marker, 'availability_bits': '100',
                  'mapping_sha256': '6' * 64}
        state = snapshots.RegistrySnapshotState(source, first)
        state.nonce = 'd' * 32
        self.assertIsNone(state.metadata()['final_receipt'])
        with patch.object(snapshots.bridge_gate, 'verify_bridge_observation') as bridge:
            state.verify_initial(Path('engine-output.log'))
            with patch.object(snapshots, 'verify_join_snapshot', return_value=second):
                self.assertEqual(state.verify_save(saved, Path('engine-output.log')),
                                 snapshots.receipt(saved, second))
        self.assertEqual(bridge.call_count, 2)
        self.assertEqual(bridge.call_args.kwargs['previous_run_id'], source.marker)
        self.assertEqual(state.metadata()['verified_save_count'], 1)
        self.assertEqual(state.metadata()['final_receipt']['mapping_sha256'], '6' * 64)
        self.assertEqual(state.metadata()['source_receipt']['mapping_sha256'], '5' * 64)


if __name__ == '__main__':
    unittest.main()
