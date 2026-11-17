"""Fresh-profile preparation never replaces an existing game profile."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lockstep.launcher import profile


class FreshProfileTest(unittest.TestCase):
    def test_windows_root_reparse_attributes_fail_closed(self):
        directory = 0o040700
        regular = SimpleNamespace(st_mode=directory, st_file_attributes=0x10)
        junction = SimpleNamespace(st_mode=directory, st_file_attributes=0x410)
        missing = SimpleNamespace(st_mode=directory)
        with patch.object(profile.stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400, create=True):
            self.assertTrue(profile._valid_profile_root(regular, windows=True))
            self.assertFalse(profile._valid_profile_root(junction, windows=True))
            self.assertFalse(profile._valid_profile_root(missing, windows=True))
            self.assertFalse(profile._valid_profile_root(
                SimpleNamespace(st_mode=directory, st_file_attributes=-1), windows=True))
        with patch.object(profile.stat, 'FILE_ATTRIBUTE_REPARSE_POINT', None, create=True):
            self.assertFalse(profile._valid_profile_root(regular, windows=True))

    def test_creates_empty_save_and_launcher_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            created = profile.prepare_fresh(
                profile.CAPTURE_PROFILE, ['ego_dlc_split', 'x4_lan_lab'], root=root)
            self.assertEqual(created, root / str(profile.CAPTURE_PROFILE))
            self.assertEqual(list((created / 'save').iterdir()), [])
            self.assertEqual((created / 'config.xml').read_text(), profile.config_xml(1280, 720))
            self.assertEqual((created / 'content.xml').read_text(),
                             profile.content_xml(['ego_dlc_split', 'x4_lan_lab']))

    def test_existing_profile_and_save_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / str(profile.CAPTURE_PROFILE)
            (old / 'save').mkdir(parents=True)
            save = old / 'save' / 'save_009.xml.gz'
            save.write_bytes(b'keep original')
            config = old / 'config.xml'
            config.write_text('keep settings')
            with self.assertRaises(FileExistsError):
                profile.prepare_fresh(profile.CAPTURE_PROFILE, [], root=root)
            self.assertEqual(save.read_bytes(), b'keep original')
            self.assertEqual(config.read_text(), 'keep settings')

    def test_invalid_input_does_not_create_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for number, names, options in [
                (123, [], {}), (45841.0, [], {}),
                (45841, ['invalid" /><extension'], {}),
                (45841, [], {'width': True}), (45841, [], {'height': 0}),
                (45841, [], {'fast': 1}),
            ]:
                with self.subTest(number=number, names=names, options=options):
                    with self.assertRaises(ValueError):
                        profile.prepare_fresh(number, names, root=root, **options)
                    self.assertEqual(list(root.iterdir()), [])

    def test_missing_or_linked_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                profile.prepare_fresh(45841, [], root=root / 'missing')
            link = root / 'linked'
            try:
                link.symlink_to(root, target_is_directory=True)
            except (OSError, NotImplementedError):
                return  # Windows may not permit creating symlinks for this user.
            with self.assertRaises(ValueError):
                profile.prepare_fresh(45841, [], root=link)
            self.assertFalse((root / '45841').exists())

    def test_linked_profile_cannot_modify_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'other'
            target.mkdir()
            keep = target / 'keep'
            keep.write_text('original')
            try:
                (root / '45841').symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(SystemExit):
                profile.prepare_fresh(45841, [], root=root)
            self.assertEqual(keep.read_text(), 'original')
            self.assertEqual([path.name for path in target.iterdir()], ['keep'])

    def test_write_failure_leaves_partial_profile_for_inspection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original_open = Path.open

            def fail_content(path, *args, **kwargs):
                if path.name == 'content.xml':
                    raise OSError('simulated write failure')
                return original_open(path, *args, **kwargs)

            with patch.object(Path, 'open', fail_content):
                with self.assertRaisesRegex(OSError, 'simulated'):
                    profile.prepare_fresh(45841, [], root=root)
            partial = root / '45841'
            self.assertTrue((partial / 'save').is_dir())
            self.assertTrue((partial / 'config.xml').is_file())
            with self.assertRaises(FileExistsError):
                profile.prepare_fresh(45841, [], root=root)


if __name__ == '__main__':
    unittest.main()
