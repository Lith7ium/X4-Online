"""Non-destructive launcher cleanup checks, including simulated old-Python junctions."""
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lockstep.launcher import game, profile  # noqa: E402


class ReparseSafety(unittest.TestCase):
    def test_remove_view_refuses_linked_root_before_reading_its_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_view = root / 'real-view'
            real_view.mkdir()
            (real_view / game.MARKER).write_text('owner\n')
            sentinel = real_view / 'keep.txt'
            sentinel.write_text('keep')
            linked_view = root / 'linked-view'
            if os.name == 'nt':
                game._junction(real_view, linked_view)
            else:
                linked_view.symlink_to(real_view, target_is_directory=True)

            with self.assertRaisesRegex(SystemExit, 'link; refusing'):
                game.remove_view(linked_view)
            self.assertEqual(sentinel.read_text(), 'keep')
            self.assertTrue(game.is_link_or_reparse(linked_view))

    def test_simulated_windows_reparse_directory_is_not_entered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'view'
            linked = root / 'aiscripts'
            linked.mkdir(parents=True)
            sentinel = linked / 'keep.xml'
            sentinel.write_text('keep')
            original_lstat = Path.lstat

            def windows_lstat(path):
                info = original_lstat(path)
                return SimpleNamespace(
                    st_mode=info.st_mode,
                    st_file_attributes=(stat.FILE_ATTRIBUTE_REPARSE_POINT
                                        if Path(path) == linked else 0),
                )

            with patch.object(game, '_is_windows', return_value=True), \
                    patch.object(Path, 'lstat', windows_lstat), \
                    patch.object(game.os, 'rmdir') as remove_directory:
                game._remove_owned(root)

            self.assertEqual(remove_directory.call_args_list, [call(linked), call(root)])
            self.assertEqual(sentinel.read_text(), 'keep')

    def test_simulated_windows_reparse_view_and_profile_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            view = root / 'view'
            view.mkdir()
            (view / game.MARKER).write_text('owner\n')
            sentinel = view / 'keep.txt'
            sentinel.write_text('keep')
            personal = root / '45850'
            personal.mkdir()
            profile_sentinel = personal / 'keep.txt'
            profile_sentinel.write_text('keep')
            original_lstat = Path.lstat

            def windows_lstat(path):
                info = original_lstat(path)
                return SimpleNamespace(
                    st_mode=info.st_mode,
                    st_file_attributes=(stat.FILE_ATTRIBUTE_REPARSE_POINT
                                        if Path(path) in (view, personal) else 0),
                )

            with patch.object(game, '_is_windows', return_value=True), \
                    patch.object(Path, 'lstat', windows_lstat):
                with self.assertRaisesRegex(SystemExit, 'link; refusing'):
                    game.remove_view(view)
                with self.assertRaisesRegex(SystemExit, 'link; refusing'):
                    profile.prepare(45850, [], root=root)

            self.assertEqual(sentinel.read_text(), 'keep')
            self.assertEqual(profile_sentinel.read_text(), 'keep')

    def test_missing_windows_reparse_attributes_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(game, '_is_windows', return_value=True):
                with self.assertRaisesRegex(OSError, 'cannot inspect Windows reparse'):
                    game.is_link_or_reparse(directory)


if __name__ == '__main__':
    unittest.main()
