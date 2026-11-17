import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'tools/dev/authority_fixture_single_running_measure_live.py'
spec = importlib.util.spec_from_file_location('single_measure_test_module', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SingleMeasureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.game = Path(self.directory.name)
        (self.game / "X4").write_bytes(b"test image")

    def test_lua_state_machine(self):
        subprocess.run(['luajit', 'tests/authority_fixture_single_measure.lua'], cwd=ROOT, check=True,
                       capture_output=True, text=True)

    def test_install_uses_private_overlay_and_builds_native_module(self):
        case = self.game / 'case'
        lab = case / 'extensions/x4_lan_lab'
        ui, md = lab / 'ui', lab / 'md'
        for directory in (ui, md, lab / 'native'):
            directory.mkdir(parents=True, exist_ok=True)
        (ui / 'config.lua').write_text('initial')
        (ui / 'native_gate_snapshot.lua').write_text('unused')
        (md / 'native_gate_battle.xml').write_text('unused')
        profile = case / 'profile'
        profile.mkdir()
        scripts = {name: b'fixture script' for name in module.fixture_source.SAVED_SCRIPTS}
        config, protected = module.install(case, profile, scripts, 12345, 'a' * 32,
                                           module.recovery.install_probe)
        self.assertIn('authority_single_measure_port=12345', config.read_text())
        self.assertIn('X4LAN_FIXTURE_SINGLE_MEASURE_UPDATE()',
                      (ui / 'authority_recovery_probe.lua').read_text())
        self.assertEqual((lab / 'native/x4lan_net.so').read_bytes()[:4], b'\x7fELF')
        self.assertIn(lab / 'native/x4lan_net.so', protected)
        self.assertTrue(all(path.is_relative_to(case) for path in protected))
        self.assertTrue(all((md / name).read_bytes() == data for name, data in scripts.items()))

    def test_install_fails_if_compiler_missing(self):
        # No compiler means no silently untested/native socket substitute.
        case = self.game / 'case'
        lab = case / 'extensions/x4_lan_lab'
        ui, md = lab / 'ui', lab / 'md'
        for directory in (ui, md, lab / 'native'):
            directory.mkdir(parents=True, exist_ok=True)
        config = ui / 'config.lua'
        config.write_text('X4LAN_CONFIG = {}\n')
        scripts = {name: b'fixture' for name in module.fixture_source.SAVED_SCRIPTS}
        with patch.object(module.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'compiler'):
                module.install(case, self.game, scripts, 12345, 'a' * 32, lambda *_: config)

    def test_correlated_local_resume_and_running_clock(self):
        lease = 'a' * 32
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as parent, \
             socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as child:
            parent.bind(('127.0.0.1', 0))
            child.connect(parent.getsockname())
            child.settimeout(2)
            child.send(('READY|' + lease).encode())
            errors = []
            def child_loop():
                try:
                    for operation, result, game_time in [('RESUME', 'RESUMED', '10'),
                                                          ('CLOCK', 'CLOCK_RESULT', '11')]:
                        packet = child.recv(200).decode().split('|')
                        assert packet[:2] == [operation, lease]
                        child.send(('|'.join([result, lease, packet[2], game_time])).encode())
                except BaseException as error:
                    errors.append(error)
            worker = threading.Thread(target=child_loop)
            worker.start()
            with patch.object(module.socket_check, 'socket_owner', return_value=True):
                clock = module.FixtureClock(parent, lease, (123, 456), self.game, lambda: None,
                                            time.monotonic() + 2)
                self.assertEqual(clock.resume(), 10)
                self.assertEqual(clock.sample(), 11)
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])

    def test_wrong_socket_owner_rejected_before_resume(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as parent, \
             socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as child:
            parent.bind(('127.0.0.1', 0))
            child.connect(parent.getsockname())
            child.send(('READY|' + 'a' * 32).encode())
            with patch.object(module.socket_check, 'socket_owner', return_value=False):
                clock = module.FixtureClock(parent, 'a' * 32, (123, 456), self.game, lambda: None,
                                            time.monotonic() + 2)
                with self.assertRaisesRegex(ValueError, 'socket owner'):
                    clock.resume()
                self.assertIsNone(clock.peer)

    def test_window_and_timeout_refused_before_source_or_launch(self):
        for duration, timeout in [(59, 600), (121, 600), (60, 179), (float('nan'), 600)]:
            args = type('Args', (), {'duration': duration, 'timeout': timeout})()
            with self.assertRaises(ValueError):
                module.run(args)


if __name__ == '__main__':
    unittest.main()
