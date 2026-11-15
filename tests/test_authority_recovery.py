"""Disposable file tests; no X4 process is started or loaded."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.checkpoints import CheckpointError, CheckpointStore
from authority.marker_evidence import MarkerEvidenceError
from authority.recovery import stage_confirmed_recovery


class RecoveryStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profile = self.root / 'private-profile'
        self.profile.mkdir(mode=0o700)
        self.store_dir = self.root / 'checkpoints'
        self.store_dir.mkdir()
        self.store = CheckpointStore(self.store_dir)
        self.source = self.root / 'source.gz'

    def publish(self, text, marker='a' * 32):
        if marker is not None:
            marker_xml = (b'<script><refs type="string"><ref id="42" string="' + marker.encode('ascii') +
                          b'"/></refs></script><md><script name="X4AuthorityCheckpointMarker">'
                          b'<cue name="MarkerState"><vars><value name="$marker" type="string" value="42"/>'
                          b'<value name="$loaded" type="integer"/></vars></cue></script></md>')
            text = text.replace(b'</savegame>', marker_xml + b'</savegame>').replace(b'<savegame/>', b'<savegame>' + marker_xml + b'</savegame>')
        self.source.write_bytes(gzip.compress(text))
        return self.store.publish(self.source, marker=marker)

    def test_stages_confirmed_not_newer_current_and_leaves_slot_009_free(self):
        first = self.publish(b'<savegame><first/></savegame>')
        self.store.confirm(first)
        self.publish(b'<savegame><newer/></savegame>', 'b' * 32)
        selected, target = stage_confirmed_recovery(self.store, self.profile)
        self.assertEqual(selected, first)
        self.assertEqual(target, self.profile / 'save' / 'save_008.xml.gz')
        self.assertEqual(target.read_bytes(), first.path.read_bytes())
        self.assertFalse((target.parent / 'save_009.xml.gz').exists())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_unconfirmed_or_unmarked_save_does_not_create_staging(self):
        checkpoint = self.publish(b'<savegame/>', None)
        with self.assertRaises(FileNotFoundError):
            stage_confirmed_recovery(self.store, self.profile)
        self.store.confirm(checkpoint)
        with self.assertRaises(CheckpointError):
            stage_confirmed_recovery(self.store, self.profile)
        self.assertEqual(list(self.profile.iterdir()), [])

    def test_manifest_assertion_without_saved_marker_is_not_recoverable(self):
        self.source.write_bytes(gzip.compress(b'<savegame/>'))
        checkpoint = self.store.publish(self.source, marker='a' * 32)
        self.store.confirm(checkpoint)
        with self.assertRaises(MarkerEvidenceError):
            stage_confirmed_recovery(self.store, self.profile)
        self.assertEqual(list(self.profile.iterdir()), [])

    def test_refuses_existing_files_links_and_nonprivate_profile(self):
        checkpoint = self.publish(b'<savegame/>')
        self.store.confirm(checkpoint)
        other = self.profile / 'keep'
        other.write_text('unchanged')
        with self.assertRaises(ValueError):
            stage_confirmed_recovery(self.store, self.profile)
        self.assertEqual(other.read_text(), 'unchanged')
        other.unlink()
        link = self.root / 'profile-link'
        link.symlink_to(self.profile, target_is_directory=True)
        with self.assertRaises(ValueError):
            stage_confirmed_recovery(self.store, link)
        self.profile.chmod(0o755)
        with self.assertRaises(ValueError):
            stage_confirmed_recovery(self.store, self.profile)
        self.assertEqual(list(self.profile.iterdir()), [])

    def test_changed_save_and_failed_copy_leave_no_partial(self):
        checkpoint = self.publish(b'<savegame/>')
        self.store.confirm(checkpoint)
        checkpoint.path.write_bytes(b'broken')
        with self.assertRaises(CheckpointError):
            stage_confirmed_recovery(self.store, self.profile)
        self.assertEqual(list(self.profile.iterdir()), [])
        checkpoint = self.publish(b'<savegame><new/></savegame>')
        self.store.confirm(checkpoint)
        with mock.patch('authority.recovery.os.fsync', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                stage_confirmed_recovery(self.store, self.profile)
        self.assertEqual(list(self.profile.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
