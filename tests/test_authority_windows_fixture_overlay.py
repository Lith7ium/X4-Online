"""Synthetic files only: no X4, Windows installation, or real DLL."""
import hashlib
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import xml.etree.ElementTree as ET

from authority.experimental_windows_fixture_overlay import _ordinary, install_fixture_overlay
from authority.load_messages import Offer
from authority.trusted_marker_load_session import MarkerBoundOffer


class FixtureOverlayTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.view = root / 'view'
        (self.view / 'extensions').mkdir(parents=True)
        (self.view / '.x4ls-view').write_text('synthetic view')
        self.dll = root / 'synthetic.dll'
        self.dll.write_bytes(b'MZ synthetic test library')
        offer = Offer(world_epoch='a' * 32, connection_handle=1, baseline_id=2,
                      load_generation=3, checkpoint_id='checkpoint-' + 'b' * 32,
                      sha256='c' * 64, attempt_id='d' * 32, size=100, name='j1.xml.gz')
        self.options = dict(new_test_view=True, bound_offer=MarkerBoundOffer(offer, 'e' * 32),
                            save_path=r'C:\private\45841\save', participant_port=20123,
                            participant_lease='f' * 32, windows_dll=self.dll,
                            dll_sha256=hashlib.sha256(self.dll.read_bytes()).hexdigest())

    def install(self, **changes):
        return install_fixture_overlay(self.view, **(self.options | changes))

    def test_overlay_contains_ordered_fixture_hooks_and_windows_dll(self):
        manifest = self.install()
        target = self.view / 'extensions/x4_lan_lab'
        for name, digest in manifest.items():
            self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), digest)
        self.assertEqual((target / 'native/x4lan_net_64.dll').read_bytes(), self.dll.read_bytes())
        ui = ET.parse(target / 'ui.xml').getroot()
        paths = [item.attrib['name'] for item in ui.iter('file')]
        for before, after in [('ui/authority_identity_probe.lua', 'ui/authority_download_load_probe.lua'),
                              ('ui/authority_checkpoint_marker_probe.lua', 'ui/authority_download_load_probe.lua'),
                              ('ui/local_udp_module.lua', 'ui/authority_two_x4_participant_probe.lua')]:
            self.assertLess(paths.index(before), paths.index(after))
        load = (target / 'ui/authority_download_load_probe.lua').read_text()
        self.assertLess(load.index('X4LAN_AUTHORITY_MARKER_READY()'), load.index('X4LAN_IDENTITY_READY()'))
        self.assertLess(load.index('X4LAN_IDENTITY_READY()'), load.index('barrier.update()'))
        config = (target / 'ui/config.lua').read_text()
        self.assertIn('authority_identity_phase="load"', config)
        self.assertIn('authority_marker_phase="load"', config)
        self.assertNotIn('e' * 32, config)  # observed from the saved world, not the expected marker
        self.assertIn('authority_participant_port=20123', config)

    def test_existing_extension_is_never_modified(self):
        target = self.view / 'extensions/x4_lan_lab'
        target.mkdir()
        keep = target / 'keep'
        keep.write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            self.install()
        self.assertEqual(keep.read_bytes(), b'original')
        self.assertEqual([path.name for path in target.iterdir()], ['keep'])

    def test_installed_registry_gate_executes_before_pause_receipt(self):
        manifest = self.install(registry_status=('ready', '1' * 32, 3, '2' * 64),
                                registry_nonce='3' * 32)
        target = self.view / 'extensions/x4_lan_lab'
        for name, digest in manifest.items():
            self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), digest)
        paths = [item.attrib['name'] for item in ET.parse(target / 'ui.xml').iter('file')]
        self.assertLess(paths.index('ui/recovery_registry_status.lua'),
                        paths.index('ui/authority_download_load_probe.lua'))
        self.assertIn('md/authority_ship_registry.xml', manifest)
        root = Path(__file__).resolve().parents[1]
        for mode in ('ready', 'wrong_count'):
            with self.subTest(mode=mode):
                subprocess.run(['luajit', str(root / 'tests/authority_windows_registry_gate.lua'),
                                str(target / 'ui'), mode], check=True, capture_output=True, cwd=root)

    def test_incomplete_registry_options_leave_no_overlay(self):
        for changes in ({'registry_nonce': '3' * 32},
                        {'registry_status': ('ready', '1' * 32, 3, '2' * 64)},
                        {'registry_status': ('ready', '1' * 32, True, '2' * 64),
                         'registry_nonce': '3' * 32}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.install(**changes)
            self.assertEqual(list((self.view / 'extensions').iterdir()), [])

    def test_bad_input_fails_before_creating_any_extension(self):
        for changes in ({'new_test_view': False}, {'participant_port': 0},
                        {'participant_lease': 'bad'}, {'dll_sha256': '0' * 64},
                        {'save_path': r'C:\Users\someone\save'},
                        {'save_path': r'C:\private\45841\..\save'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.install(**changes)
                self.assertEqual(list((self.view / 'extensions').iterdir()), [])

    def test_write_failure_leaves_partial_extension_without_deletion(self):
        original = Path.open
        def interrupted(path, *args, **kwargs):
            if path.name == 'x4_control_engine.lua' and args and args[0] == 'xb':
                raise OSError('simulated failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', interrupted):
            with self.assertRaises(OSError):
                self.install()
        target = self.view / 'extensions/x4_lan_lab'
        self.assertTrue((target / 'ui/client_load_barrier.lua').is_file())
        with self.assertRaises(FileExistsError):
            self.install()

    def test_linked_extension_root_is_refused(self):
        extensions = self.view / 'extensions'
        extensions.rmdir()
        other = self.view.parent / 'other'
        other.mkdir()
        try:
            extensions.symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(list(other.iterdir()), [])

    def test_reparse_attributes_are_refused(self):
        for attributes in (0x410, None, -1):
            info = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=attributes)
            with self.subTest(attributes=attributes), \
                 patch.object(Path, 'lstat', return_value=info), \
                 patch.object(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400, create=True):
                with self.assertRaises(ValueError):
                    _ordinary(self.view, directory=True)


if __name__ == '__main__':
    unittest.main()
