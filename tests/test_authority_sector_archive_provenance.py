"""Synthetic verifier wiring and filesystem rejection; no X4 or archived save."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.checkpoints import Checkpoint
import authority_sector_archive_provenance as subject


class ArchiveProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Path(self.temp.name) / 'checkpoints'
        self.folder = self.store / subject.CHECKPOINT_ID
        self.folder.mkdir(parents=True)
        self.save = self.folder / 'save.xml.gz'
        self.save.write_bytes(b'synthetic')
        (self.folder / 'manifest.json').write_bytes(b'fixture manifest')
        (self.store / 'CURRENT').write_bytes(b'fixture pointer')
        (self.store / 'CONFIRMED').write_bytes(b'fixture pointer')
        self.historical = self.store.parent / 'result.json'
        self.historical.write_text('{"success": false, "error": "invalid fixture index"}\n')
        self.checkpoint = Checkpoint(subject.CHECKPOINT_ID, self.save, subject.SHA256, subject.SIZE)
        self.evidence = {'slots_checked': 2, 'saved_ship_sector_ancestry_matches': True,
                         'runtime_binding_proven': False, 'exact_loaded_file_proven': False,
                         'universe_coverage_proven': False}
        self.cp_patch = patch.object(subject.CheckpointStore, 'latest_confirmed', return_value=self.checkpoint)
        self.marker_patch = patch.object(subject, 'verify_saved_marker', return_value=True)
        self.sector_patch = patch.object(subject.sector_evidence, 'verify', return_value=self.evidence)
        self.cp_mock = self.cp_patch.start(); self.addCleanup(self.cp_patch.stop)
        self.marker_mock = self.marker_patch.start(); self.addCleanup(self.marker_patch.stop)
        self.sector_mock = self.sector_patch.start(); self.addCleanup(self.sector_patch.stop)

    def test_checks_confirmed_marker_and_epoch_without_historical_result(self):
        before = self.historical.read_bytes(), self.historical.stat().st_mtime_ns
        result = subject.verify(self.store)
        self.cp_mock.assert_called_once()
        self.marker_mock.assert_called_once_with(self.checkpoint, subject.MARKER,
            script_name='X4AuthorityCheckpointMarker', cue_name='Store')
        self.sector_mock.assert_called_once_with(self.checkpoint, subject.REGISTRY_EPOCH)
        self.assertTrue(result['current_equals_confirmed'])
        self.assertFalse(result['exact_loaded_file_proven'])
        self.assertFalse(result['historical_result_reinterpreted'])
        self.assertEqual((self.historical.read_bytes(), self.historical.stat().st_mtime_ns), before)

    def test_unconfirmed_current_and_unexpected_checkpoint_refused(self):
        (self.store / 'CURRENT').write_bytes(b'other pointer')
        with self.assertRaisesRegex(ValueError, 'not the confirmed'): subject.verify(self.store)
        (self.store / 'CURRENT').write_bytes(b'fixture pointer')
        self.cp_mock.return_value = Checkpoint(subject.CHECKPOINT_ID, self.save, 'f' * 64, subject.SIZE)
        with self.assertRaisesRegex(ValueError, 'differs'): subject.verify(self.store)

    def test_missing_or_mismatched_evidence_refused(self):
        self.marker_mock.return_value = False
        with self.assertRaisesRegex(ValueError, 'marker'): subject.verify(self.store)
        self.marker_mock.return_value = True
        self.sector_mock.return_value = dict(self.evidence, slots_checked=1)
        with self.assertRaisesRegex(ValueError, 'sector evidence'): subject.verify(self.store)

    def test_evidence_change_or_symlink_refused(self):
        def mutate(*_args, **_kwargs):
            self.save.write_bytes(b'changed')
            return True
        self.marker_mock.side_effect = mutate
        with self.assertRaisesRegex(ValueError, 'changed'): subject.verify(self.store)
        self.marker_mock.side_effect = None
        self.save.unlink(); self.save.symlink_to(self.folder / 'manifest.json')
        with self.assertRaisesRegex(ValueError, 'symlink'): subject.verify(self.store)

    def test_parent_symlink_refused(self):
        alias = self.store.parent / 'alias'; alias.symlink_to(self.store, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'): subject.verify(alias)


if __name__ == '__main__':
    unittest.main()
