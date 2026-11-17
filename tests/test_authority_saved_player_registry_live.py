"""Offline integration checks for saved fixture enrollment and seat ordering."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import authority_saved_player_registry_live as subject


class SavedPlayerRegistryIntegrationTests(unittest.TestCase):
    def test_registry_and_seat_use_one_checked_log_snapshot_per_poll(self):
        marker = 'a' * 32
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'engine.log'
            rows = ['[X4LAN] AUTH_RECOVERY REQUEST',
                    '[X4LAN] AUTH_MARKER load INSPECTED ' + marker,
                    '[X4LAN] AUTH_RECOVERY PAUSED',
                    subject.REGISTRY_TAG + subject.EXPECTED_RECEIPT]
            controls = [subject.seat.CONTROL_TAG + value for value in subject.seat.EXPECTED_CONTROL]
            rows += controls[:5] + [subject.seat.ACTION_TAG + 'ACTION_BEGIN',
                                    subject.seat.ACTION_TAG + 'ACTION_RETURNED'] + controls[5:]
            path.write_text('\n'.join(rows) + '\n')
            watch = subject.SavedRegistryWatch(path, marker)
            with patch.object(subject.seat.fixture_log, 'capture', wraps=subject.seat.fixture_log.capture) as capture:
                self.assertTrue(watch.poll())
                self.assertEqual(capture.call_count, 1)
            with path.open('a') as stream:
                stream.write(subject.REGISTRY_TAG + 'ERROR\n')
            with self.assertRaises(ValueError):
                watch.poll()

    def test_registry_receipt_must_be_unique_after_pause_and_before_seat(self):
        pause = '[X4LAN] AUTH_RECOVERY PAUSED'
        registered = subject.REGISTRY_TAG + subject.EXPECTED_RECEIPT
        seat_start = subject.seat.CONTROL_TAG + 'START'
        raw = lambda lines: ('\n'.join(lines) + '\n').encode()
        self.assertTrue(subject.check_registry_log(raw([pause, registered, seat_start]), partial=False))
        self.assertFalse(subject.check_registry_log(raw([pause]), partial=True))
        for lines in ([registered, pause, seat_start], [pause, seat_start, registered],
                      [pause, registered, registered, seat_start], [pause, subject.REGISTRY_TAG + 'ERROR']):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                subject.check_registry_log(raw(lines), partial=True)

    def test_install_preserves_saved_scripts_and_one_update_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / 'case'
            profile = case / 'profile'
            lab = case / 'extensions/x4_lan_lab'
            ui, md = lab / 'ui', lab / 'md'
            ui.mkdir(parents=True); md.mkdir(); profile.mkdir()
            scripts = {name: ('original:' + name).encode() for name in subject.seat.fixture_source.SAVED_SCRIPTS}
            recovery_installer = object()

            def seat_installer(case_arg, profile_arg, saved, *, slot, nonce, timeout, original_install):
                self.assertEqual((case_arg, profile_arg, saved), (case, profile, scripts))
                self.assertIs(original_install, recovery_installer)
                self.assertEqual(slot, 2)
                for name, contents in saved.items():
                    (md / name).write_bytes(contents)
                (ui / 'authority_saved_player_control_owner.lua').write_text(
                    'function X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()\nend\n')
                (lab / 'ui.xml').write_text('    <file name="ui/authority_recovery_probe.lua" />\n')
                config = ui / 'config.lua'; config.write_text('X4LAN_CONFIG = {}\n')
                return config, [ui / 'authority_saved_player_control_owner.lua']

            config, protected = subject.install(case, profile, scripts, slot=2, nonce='a'*32, timeout=60,
                seat_installer=seat_installer, recovery_installer=recovery_installer, registry_nonce='b'*32)
            for name, contents in scripts.items():
                self.assertEqual((md / name).read_bytes(), contents)
            self.assertIn(md / 'authority_player_registry_read.xml', protected)
            self.assertIn(ui / 'authority_saved_player_registry_dispatch.lua', protected)
            self.assertIn('X4LAN_AUTHORITY_RECOVERY_SEAT_TICK',
                          (ui / 'authority_saved_player_control_owner.lua').read_text())
            self.assertIn('authority_registry_enroll_nonce="' + 'b'*32 + '"', config.read_text())
            manifest = (lab / 'ui.xml').read_text()
            self.assertLess(manifest.index('authority_saved_player_registry_dispatch.lua'),
                            manifest.index('authority_recovery_probe.lua'))

    def test_runner_restores_seat_hooks_after_failure(self):
        original_install, original_watch = subject.seat.install, subject.seat.SavedControlWatch
        with patch.object(subject.seat, 'run', side_effect=RuntimeError('failed before launch')):
            with self.assertRaisesRegex(RuntimeError, 'failed before launch'):
                subject.run(SimpleNamespace())
        self.assertIs(subject.seat.install, original_install)
        self.assertIs(subject.seat.SavedControlWatch, original_watch)

    def test_concrete_seat_and_recovery_installers_are_composed(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / 'case'
            profile = case / 'profile'
            lab = case / 'extensions/x4_lan_lab'
            ui, md = lab / 'ui', lab / 'md'
            ui.mkdir(parents=True); md.mkdir(); (profile / 'save').mkdir(parents=True)
            for path in (ui / 'native_gate_snapshot.lua', md / 'native_gate_battle.xml', ui / 'config.lua'):
                path.write_text('test')
            source = subject.seat.fixture_source
            scripts = {}
            for name in source.SAVED_SCRIPTS:
                path = (source.fixture_save.historical_registry() if name == 'authority_ship_registry.xml'
                        else ROOT / 'tools/dev' / name)
                scripts[name] = path.read_bytes()
            config, protected = subject.install(case, profile, scripts, slot=1, nonce='a'*32, timeout=60,
                seat_installer=subject.seat.install, recovery_installer=subject.seat.recovery.install_probe,
                registry_nonce='b'*32)
            self.assertIn('authority_fixture_slot=1', config.read_text())
            for name, contents in scripts.items():
                self.assertEqual((md / name).read_bytes(), contents)
            self.assertIn(ui / 'authority_saved_player_control_owner.lua', protected)
            self.assertIn(ui / 'authority_saved_player_registry_dispatch.lua', protected)
            self.assertEqual((ui / 'authority_recovery_probe.lua').read_text().count("SetScript('onUpdate'"), 1)

    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_dispatch_orders_registry_before_seat_and_fences_late_events(self):
        subprocess.run(['luajit', 'tests/authority_saved_player_registry_dispatch.lua'],
                       cwd=ROOT, check=True, timeout=10, capture_output=True)

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'), 'LuaJIT and C compiler required')
    def test_real_dispatcher_and_registry_owner_with_synthetic_x4_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / 'fake-x4.so'
            subprocess.run(['cc', '-shared', '-fPIC', 'tests/lua/authority_player_seat_fake_x4.c',
                            'tests/lua/authority_player_registry_fake_x4.c', '-o', str(library)],
                           cwd=ROOT, check=True, timeout=10, capture_output=True)
            subprocess.run(['luajit', 'tests/authority_saved_player_registry_dispatch_x4.lua', str(library)],
                           cwd=ROOT, check=True, timeout=10, capture_output=True)
