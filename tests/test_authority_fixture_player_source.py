import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import authority_fixture_player_source_arm as arm
import authority_fixture_player_source_install as installer


class FixturePlayerSourceTests(unittest.TestCase):
    def test_owner_lifecycle(self):
        subprocess.run(['luajit', 'tests/authority_fixture_player_source.lua'], cwd=ROOT, check=True)

    def test_arm_accepts_exact_owned_ready_and_sends_arm(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.bind(('127.0.0.1', 0))
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.connect(listener.getsockname())
        tokens = ['a' * 32, 'b' * 32, 'c' * 32, 'd' * 32]
        ready = ('READY|' + '|'.join(tokens)).encode()
        peer.send(ready)
        with patch.object(arm, 'check_process'), patch.object(arm, 'socket_owner', return_value=True):
            address = arm.arm_fixture_source(listener, process={'pid': 1}, lease=tokens[0], attempt=tokens[1],
                epoch=tokens[2], generation=tokens[3], guard=lambda: True, running=lambda: True, timeout=1)
        self.assertEqual(address, peer.getsockname())
        self.assertEqual(peer.recv(512), ('ARM|' + '|'.join(tokens)).encode())
        listener.close(); peer.close()

    def test_arm_rejects_wrong_owner_and_closes_socket(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.bind(('127.0.0.1', 0))
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.connect(listener.getsockname())
        tokens = ['a' * 32, 'b' * 32, 'c' * 32, 'd' * 32]
        peer.send(('READY|' + '|'.join(tokens)).encode())
        with patch.object(arm, 'check_process'), patch.object(arm, 'socket_owner', return_value=False):
            with self.assertRaises(RuntimeError):
                arm.arm_fixture_source(listener, process={'pid': 1}, lease=tokens[0], attempt=tokens[1],
                    epoch=tokens[2], generation=tokens[3], guard=lambda: True, running=lambda: True, timeout=1)
        self.assertEqual(listener.fileno(), -1)
        peer.close()

    def test_arm_aborts_promptly_when_context_is_lost(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.bind(('127.0.0.1', 0))
        count = 0
        def guard():
            nonlocal count
            count += 1
            return count < 2
        tokens = ['a' * 32, 'b' * 32, 'c' * 32, 'd' * 32]
        with patch.object(arm, 'check_process'):
            with self.assertRaises(RuntimeError):
                arm.arm_fixture_source(listener, process={'pid': 1}, lease=tokens[0], attempt=tokens[1],
                    epoch=tokens[2], generation=tokens[3], guard=guard, running=lambda: True, timeout=2)
        self.assertEqual(count, 2)
        self.assertEqual(listener.fileno(), -1)

    def test_partial_secret_write_restores_original_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.lua'
            original = b'X4LAN_CONFIG={}\n'
            config.write_bytes(original)
            real_write = installer.os.write
            calls = 0
            def failing_write(fd, data):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return real_write(fd, data[:8])
                if calls == 2:
                    raise OSError('injected partial write')
                return real_write(fd, data)
            with patch.object(installer.os, 'write', side_effect=failing_write):
                with self.assertRaisesRegex(OSError, 'injected partial write'):
                    installer._write_config_transaction(config, original, b'secret replacement', [config], {})
            self.assertEqual(config.read_bytes(), original)

    def test_replaced_config_is_never_overwritten_during_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.lua'
            original = b'X4LAN_CONFIG={}\n'
            config.write_bytes(original)
            moved = config.with_name('moved.lua')
            def replace_then_fail(fd, data):
                config.rename(moved)
                config.write_bytes(b'foreign file')
                raise OSError('injected concurrent replacement')
            with patch.object(installer.os, 'write', side_effect=replace_then_fail):
                with self.assertRaises(BaseExceptionGroup):
                    installer._write_config_transaction(config, original, b'secret replacement', [config], {})
            self.assertEqual(config.read_bytes(), b'foreign file')
            self.assertEqual(moved.read_bytes(), original)

    def test_handle_creation_failure_precedes_secret_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.lua'
            original = b'X4LAN_CONFIG={}\n'
            config.write_bytes(original)
            with patch.object(installer, 'Installation', side_effect=OSError('injected handle failure')):
                with self.assertRaises(OSError):
                    installer._write_config_transaction(config, original, b'secret replacement', [config], {})
            self.assertEqual(config.read_bytes(), original)

    def test_installs_private_overlay_with_seat_gate_and_existing_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp); profile = case / '45841'; profile.mkdir()
            lab = case / 'extensions/x4_lan_lab'; ui = lab / 'ui'; md = lab / 'md'
            ui.mkdir(parents=True); md.mkdir()
            (lab / 'ui.xml').write_text('    <file name="ui/authority_download_load_probe.lua" />\n')
            (ui / 'config.lua').write_text('X4LAN_CONFIG={}\n')
            (ui / 'authority_download_load_probe.lua').write_text('  if not X4LAN_REGISTERED_PLAYER_CONTROL_TICK() then return end\n')
            (ui / 'authority_two_x4_participant_probe.lua').write_bytes((ROOT / 'tools/dev/authority_two_x4_participant_probe.lua').read_bytes())
            installation = installer.install(case, profile, slot=1, epoch='a'*32, sector='sector_1', lease='b'*32,
                attempt='c'*32, generation='d'*32, bootstrap_nonce='e'*32, sampler_nonce='f'*32,
                port=12345, timeout=20)
            self.assertTrue(all(path.exists() for path in installation.paths))
            config = (ui / 'config.lua').read_text()
            self.assertNotIn('latest_cache', config)
            self.assertFalse((ui / 'fixture_player_latest_cache.lua').exists())
            self.assertIn('slot=1', config)
            self.assertIn('port=12345', config)
            self.assertIn('X4LAN_FIXTURE_SEAT_READY=true', (ui / 'authority_download_load_probe.lua').read_text())
            self.assertIn('fixture_source:tick()', (ui / 'authority_two_x4_participant_probe.lua').read_text())
            installation.redact()
            redacted = (ui / 'config.lua').read_text()
            self.assertNotIn(installer.lua_literal('a'*32), redacted)
            self.assertEqual(redacted.count(installer.lua_literal('redacted')), 6)
            with self.assertRaises(ValueError):
                installation.redact()


if __name__ == '__main__':
    unittest.main()
