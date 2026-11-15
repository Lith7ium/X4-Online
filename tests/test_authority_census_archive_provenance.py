"""Synthetic wrapper checks; these do not read the archived checkpoint or run X4."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.checkpoints import Checkpoint
import authority_census_archive_provenance as subject


class CensusArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Path(self.temp.name) / 'checkpoints'
        folder = self.store / subject.CHECKPOINT_ID
        folder.mkdir(parents=True)
        self.save = folder / 'save.xml.gz'
        self.save.write_bytes(b'synthetic')
        (folder / 'manifest.json').write_bytes(b'manifest')
        (self.store / 'CURRENT').write_bytes(b'pointer')
        (self.store / 'CONFIRMED').write_bytes(b'pointer')
        self.checkpoint = Checkpoint(subject.CHECKPOINT_ID, self.save, subject.SHA256, subject.SIZE)
        self.evidence = {'count': subject.COUNT, 'unique_saved_components': subject.COUNT,
                         'forward_reverse_match': True, 'runtime_binding_proven': False,
                         'universe_coverage_proven': False}
        self.store_patch = patch.object(subject.CheckpointStore, 'latest_confirmed', return_value=self.checkpoint)
        self.marker_patch = patch.object(subject, 'verify_saved_marker', return_value=True)
        self.registry_patch = patch.object(subject.registry, 'verify', return_value=self.evidence)
        self.cp = self.store_patch.start(); self.addCleanup(self.store_patch.stop)
        self.marker = self.marker_patch.start(); self.addCleanup(self.marker_patch.stop)
        self.registry = self.registry_patch.start(); self.addCleanup(self.registry_patch.stop)

    def test_expected_checkpoint_marker_and_registry_are_checked(self):
        result = subject.verify(self.store)
        self.marker.assert_called_once_with(self.checkpoint, subject.MARKER,
            script_name='X4AuthorityCheckpointMarker', cue_name='Store')
        self.registry.assert_called_once_with(self.checkpoint, subject.REGISTRY_EPOCH, subject.COUNT)
        self.assertEqual(result['registry_entries'], 10054)
        self.assertFalse(result['runtime_binding_proven'])
        self.assertFalse(result['universe_coverage_proven'])

    def test_mismatched_pointer_checkpoint_or_evidence_is_refused(self):
        (self.store / 'CURRENT').write_bytes(b'other')
        with self.assertRaisesRegex(ValueError, 'not confirmed'): subject.verify(self.store)
        (self.store / 'CURRENT').write_bytes(b'pointer')
        self.cp.return_value = Checkpoint(subject.CHECKPOINT_ID, self.save, 'f' * 64, subject.SIZE)
        with self.assertRaisesRegex(ValueError, 'differs'): subject.verify(self.store)
        self.cp.return_value = self.checkpoint
        self.marker.return_value = False
        with self.assertRaisesRegex(ValueError, 'marker'): subject.verify(self.store)
        self.marker.return_value = True
        self.registry.return_value = dict(self.evidence, forward_reverse_match=False)
        with self.assertRaisesRegex(ValueError, 'registry evidence'): subject.verify(self.store)

    def test_mutation_and_symlink_are_refused(self):
        def mutate(*args, **kwargs):
            self.save.write_bytes(b'changed')
            return True
        self.marker.side_effect = mutate
        with self.assertRaisesRegex(ValueError, 'changed'): subject.verify(self.store)
        self.marker.side_effect = None
        self.save.unlink(); self.save.symlink_to(self.save.parent / 'manifest.json')
        with self.assertRaisesRegex(ValueError, 'symlink'): subject.verify(self.store)


if __name__ == '__main__':
    unittest.main()
