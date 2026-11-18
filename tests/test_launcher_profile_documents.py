import ctypes
import os
from pathlib import Path, PureWindowsPath
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lockstep.launcher import profile  # noqa: E402


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *arguments):
        return self.callback(*arguments)


class LauncherProfileDocumentsTests(unittest.TestCase):
    def fake_windows_api(self, path_text=None, result=0):
        path_buffer = ctypes.create_unicode_buffer(path_text) if path_text is not None else None
        freed_addresses = []
        observed_call = {}

        def get_known_folder_path(guid_pointer, flags, token, output_pointer):
            folder_id = ctypes.cast(
                guid_pointer, ctypes.POINTER(profile._KnownFolderId),
            ).contents
            observed_call['guid'] = (
                folder_id.data1, folder_id.data2, folder_id.data3, tuple(folder_id.data4),
            )
            observed_call['flags'] = flags
            observed_call['token'] = token
            if path_buffer is not None:
                output = ctypes.cast(output_pointer, ctypes.POINTER(ctypes.c_void_p))
                output[0] = ctypes.cast(path_buffer, ctypes.c_void_p)
            return result

        def free_task_memory(pointer):
            freed_addresses.append(pointer.value)

        shell32 = type('FakeShell32', (), {
            'SHGetKnownFolderPath': FakeFunction(get_known_folder_path),
        })()
        ole32 = type('FakeOle32', (), {
            'CoTaskMemFree': FakeFunction(free_task_memory),
        })()

        def load_library(name):
            if name == 'shell32':
                return shell32
            if name == 'ole32':
                return ole32
            raise AssertionError(f'unexpected DLL: {name}')

        return load_library, path_buffer, freed_addresses, observed_call

    def test_windows_documents_uses_redirected_unicode_known_folder_and_frees_it(self):
        path_text = r'C:\Users\Zoë\OneDrive - Example\文書'
        load_library, path_buffer, freed, observed = self.fake_windows_api(path_text)
        with patch.object(profile.sys, 'platform', 'win32'), \
                patch.object(profile, 'Path', PureWindowsPath), \
                patch.object(ctypes, 'WinDLL', side_effect=load_library, create=True):
            result = profile.documents()

        self.assertEqual(result, PureWindowsPath(path_text) / 'Egosoft' / 'X4')
        self.assertEqual(observed['guid'], (
            0xFDD39AD0, 0x238F, 0x46AF, (0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
        ))
        self.assertEqual(observed['flags'], 0)
        self.assertIsNone(observed['token'])
        self.assertEqual(freed, [ctypes.addressof(path_buffer)])

    def test_windows_documents_frees_error_output_and_raises_hresult(self):
        failure = ctypes.c_int32(0x80004005).value
        load_library, path_buffer, freed, _ = self.fake_windows_api(r'C:\redirected', failure)
        with patch.object(profile.sys, 'platform', 'win32'), \
                patch.object(ctypes, 'WinDLL', side_effect=load_library, create=True):
            with self.assertRaisesRegex(OSError, 'HRESULT 0x80004005'):
                profile.documents()
        self.assertEqual(freed, [ctypes.addressof(path_buffer)])

    def test_windows_documents_rejects_success_with_null_path(self):
        load_library, _, freed, _ = self.fake_windows_api()
        with patch.object(profile.sys, 'platform', 'win32'), \
                patch.object(ctypes, 'WinDLL', side_effect=load_library, create=True):
            with self.assertRaisesRegex(OSError, 'without returning a path'):
                profile.documents()
        self.assertEqual(freed, [])

    def test_non_windows_documents_keeps_userprofile_behavior(self):
        with patch.object(profile.sys, 'platform', 'linux'), \
                patch.dict(os.environ, {'USERPROFILE': '/tmp/profile-root'}):
            self.assertEqual(
                profile.documents(), Path('/tmp/profile-root') / 'Documents' / 'Egosoft' / 'X4',
            )


if __name__ == '__main__':
    unittest.main()
