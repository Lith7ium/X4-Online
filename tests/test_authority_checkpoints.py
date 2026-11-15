"""Synthetic, disposable-file tests; these do not run X4 or load an actual save."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.checkpoints import CheckpointError, CheckpointStore


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store_dir = self.root / 'store'
        self.store_dir.mkdir()
        self.source = self.root / 'incoming.gz'
        self.store = CheckpointStore(self.store_dir)

    def write_save(self, text=b'<savegame><info seed="123"/></savegame>'):
        self.source.write_bytes(gzip.compress(text))

    def test_publish_restart_and_verify_previous_generation(self):
        self.write_save()
        first = self.store.publish(self.source)
        self.write_save(b'<savegame><info seed="456"/></savegame>')
        second = self.store.publish(self.source)
        restarted = CheckpointStore(self.store_dir)
        self.assertEqual(restarted.latest(), second)
        self.assertEqual(restarted.get(first.checkpoint_id), first)
        self.assertEqual(second.sha256, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertNotEqual(first.sha256, second.sha256)

    def test_confirmed_pointer_survives_a_new_unconfirmed_publication(self):
        self.write_save()
        first = self.store.publish(self.source)
        self.store.confirm(first)
        self.write_save(b'<savegame><info seed="456"/></savegame>')
        second = self.store.publish(self.source)
        restarted = CheckpointStore(self.store_dir)
        self.assertEqual(restarted.latest(), second)
        self.assertEqual(restarted.latest_confirmed(), first)
        with self.assertRaises(CheckpointError):
            restarted.confirm(first)
        self.assertEqual(restarted.latest_confirmed(), first)
        restarted.confirm(second)
        self.assertEqual(CheckpointStore(self.store_dir).latest_confirmed(), second)

    def test_confirmation_replace_failure_keeps_previous_pointer(self):
        self.write_save()
        first = self.store.publish(self.source)
        self.store.confirm(first)
        self.write_save(b'<savegame><different/></savegame>')
        second = self.store.publish(self.source)
        with mock.patch('authority.checkpoints.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.store.confirm(second)
        self.assertEqual(CheckpointStore(self.store_dir).latest_confirmed(), first)
        self.assertEqual(self.store.latest(), second)
        self.assertFalse(list(self.store_dir.glob('.confirmed-*')))

    def test_confirmed_pointer_revalidates_and_never_falls_back(self):
        self.write_save()
        first = self.store.publish(self.source)
        with self.assertRaises(FileNotFoundError):
            self.store.latest_confirmed()
        self.store.confirm(first)
        self.write_save(b'<savegame><different/></savegame>')
        self.store.publish(self.source)
        first.path.write_bytes(b'corrupt')
        with self.assertRaises(CheckpointError):
            self.store.latest_confirmed()

    def test_invalid_gzip_or_xml_never_replaces_previous(self):
        self.write_save()
        previous = self.store.publish(self.source)
        valid = self.source.read_bytes()
        cases = [b'', b'not gzip', valid[:-4], valid[:-8] + b'badbytes',
                 gzip.compress(b'<savegame><unclosed></savegame>'),
                 gzip.compress(b'<wrong/>'),
                 gzip.compress(b'<!DOCTYPE savegame [<!ENTITY x "bad">]><savegame>&x;</savegame>')]
        for invalid in cases:
            with self.subTest(data=invalid[:20]):
                self.source.write_bytes(invalid)
                with self.assertRaises(CheckpointError):
                    self.store.publish(self.source)
                self.assertEqual(CheckpointStore(self.store_dir).latest(), previous)

    def test_failed_atomic_pointer_publish_keeps_previous_and_ignores_orphan(self):
        self.write_save()
        previous = self.store.publish(self.source)
        self.write_save(b'<savegame><different/></savegame>')
        with mock.patch('authority.checkpoints.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.store.publish(self.source)
        self.assertEqual(CheckpointStore(self.store_dir).latest(), previous)
        self.assertEqual(len(list(self.store_dir.glob('checkpoint-*'))), 2)
        self.assertFalse(list(self.store_dir.glob('.staging-*')))
        self.assertFalse(list(self.store_dir.glob('.current-*')))

    def test_tampering_with_content_manifest_or_pointer_fails_closed(self):
        self.write_save()
        checkpoint = self.store.publish(self.source)
        pointer = self.store_dir / 'CURRENT'
        manifest = checkpoint.path.parent / 'manifest.json'
        original_pointer = pointer.read_bytes()
        original_manifest = manifest.read_bytes()
        original_save = checkpoint.path.read_bytes()
        checkpoint.path.write_bytes(original_save[:-1] + bytes([original_save[-1] ^ 1]))
        with self.assertRaises(CheckpointError):
            self.store.latest()
        checkpoint.path.write_bytes(original_save)
        data = json.loads(original_manifest)
        data['size'] += 1
        manifest.write_text(json.dumps(data))
        with self.assertRaises(CheckpointError):
            self.store.latest()
        manifest.write_bytes(original_manifest)
        data = json.loads(original_pointer)
        data['id'] = '../outside'
        pointer.write_text(json.dumps(data))
        with self.assertRaises(CheckpointError):
            self.store.latest()
        pointer.write_bytes(original_pointer)
        self.assertEqual(self.store.latest(), checkpoint)

    def test_refuses_linked_source_inside_store_and_linked_checkpoint(self):
        self.write_save()
        checkpoint = self.store.publish(self.source)
        link = self.root / 'link.gz'
        link.symlink_to(self.source)
        with self.assertRaises(CheckpointError):
            self.store.publish(link)
        with self.assertRaises(CheckpointError):
            self.store.publish(checkpoint.path)
        save = checkpoint.path
        original = save.read_bytes()
        save.unlink()
        save.symlink_to(self.source)
        with self.assertRaises((CheckpointError, OSError)):
            self.store.latest()
        self.assertEqual(self.source.read_bytes(), original)

    def test_restart_revalidates_xml_even_when_hashes_agree(self):
        self.write_save()
        checkpoint = self.store.publish(self.source)
        invalid = gzip.compress(b'<savegame><broken></savegame>')
        checkpoint.path.write_bytes(invalid)
        manifest_path = checkpoint.path.parent / 'manifest.json'
        manifest = json.loads(manifest_path.read_bytes())
        manifest.update(size=len(invalid), sha256=hashlib.sha256(invalid).hexdigest())
        metadata = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode('ascii')
        manifest_path.write_bytes(metadata)
        pointer_path = self.store_dir / 'CURRENT'
        pointer = json.loads(pointer_path.read_bytes())
        pointer['manifest_sha256'] = hashlib.sha256(metadata).hexdigest()
        pointer_path.write_text(json.dumps(pointer))
        with self.assertRaises(CheckpointError):
            CheckpointStore(self.store_dir).latest()


if __name__ == '__main__':
    unittest.main()
