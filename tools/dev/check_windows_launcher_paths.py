"""Windows-only, disposable native checks for launcher junctions and fixture ACLs.

Run directly on Windows with Python 3.10, 3.11, and 3.12. No X4 installation,
profile, or account settings are touched; all paths live below TemporaryDirectory.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

if os.name != 'nt':
    raise SystemExit('Windows required for native junction and icacls checks')

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from authority import windows_fixture_workspace as fixture  # noqa: E402
from lockstep.launcher import game, profile  # noqa: E402


class NativeWindowsPaths(unittest.TestCase):
    def test_view_cleanup_unlinks_real_junctions_and_preserves_fake_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = root / 'fake-install'
            (install / 'aiscripts').mkdir(parents=True)
            (install / 'aiscripts' / 'keep.xml').write_text('keep')
            (install / 'extensions' / 'ego_dlc_test').mkdir(parents=True)
            (install / 'extensions' / 'ego_dlc_test' / 'keep.xml').write_text('keep')
            (install / 'X4.exe').write_bytes(b'fake executable')

            view = game.create_view(install, root / 'view')
            self.assertTrue(game.is_link_or_reparse(view / 'aiscripts'))
            self.assertTrue(game.is_link_or_reparse(view / 'extensions' / 'ego_dlc_test'))
            game.remove_view(view)

            self.assertFalse(view.exists())
            self.assertEqual((install / 'aiscripts' / 'keep.xml').read_text(), 'keep')
            self.assertEqual((install / 'extensions' / 'ego_dlc_test' / 'keep.xml').read_text(), 'keep')
            self.assertEqual((install / 'X4.exe').read_bytes(), b'fake executable')

    def test_linked_roots_are_refused_without_touching_sentinels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_view = root / 'real-view'
            real_view.mkdir()
            (real_view / game.MARKER).write_text('fake install\n')
            view_sentinel = real_view / 'keep.txt'
            view_sentinel.write_text('keep view')
            linked_view = root / 'linked-view'
            game._junction(real_view, linked_view)
            try:
                with self.assertRaisesRegex(SystemExit, 'link; refusing'):
                    game.remove_view(linked_view)
                self.assertEqual(view_sentinel.read_text(), 'keep view')
            finally:
                os.rmdir(linked_view)

            real_profile = root / 'real-profile'
            real_profile.mkdir()
            profile_sentinel = real_profile / 'keep.txt'
            profile_sentinel.write_text('keep profile')
            linked_profile = root / '45850'
            game._junction(real_profile, linked_profile)
            try:
                with self.assertRaisesRegex(SystemExit, 'link; refusing'):
                    profile.prepare(45850, [], root=root)
                self.assertEqual(profile_sentinel.read_text(), 'keep profile')
            finally:
                os.rmdir(linked_profile)

    def test_fixture_acl_commands_work_on_owned_temporary_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'owned'
            directory.mkdir()
            file_path = directory / 'settings.txt'
            file_path.write_text('fixture')
            sid = fixture._current_sid()
            fixture._restrict_directory(directory, sid)
            fixture._restrict_file(file_path, sid)
            self.assertEqual(file_path.read_text(), 'fixture')


if __name__ == '__main__':
    unittest.main()
