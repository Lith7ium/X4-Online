"""Private fixture-source preparation; no X4 or worker process is started."""
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_recovered_server_client as client
import authority_fixture_player_source_install as installer


class FixtureSourceParentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.case = Path(self.temporary.name)
        self.profile = self.case / '45841'
        self.profile.mkdir()
        lab = self.case / 'extensions/x4_lan_lab'
        self.ui = lab / 'ui'
        self.ui.mkdir(parents=True)
        (lab / 'md').mkdir()
        (lab / 'ui.xml').write_text('    <file name="ui/authority_download_load_probe.lua" />\n')
        (self.ui / 'config.lua').write_text('X4LAN_CONFIG={}\n')
        (self.ui / 'authority_download_load_probe.lua').write_text(
            '  if not X4LAN_REGISTERED_PLAYER_CONTROL_TICK() then return end\n')
        (self.ui / 'authority_two_x4_participant_probe.lua').write_bytes(
            (ROOT / 'tools/dev/authority_two_x4_participant_probe.lua').read_bytes())
        self.participant = client.ServerClient(time.monotonic()+30, self.case, keep_worker=True)
        self.addCleanup(self.participant.cleanup_diagnostic)
        self.ticket = {'world_epoch': '1'*32, 'attempt_id': '2'*32}
        self.grant = {'session_epoch': '1'*32, 'epoch': 'c'*32, 'generation': 'd'*32,
                      'index': 3, 'sector_macro': 'sector_a', 'token': 'e'*32, 'incarnation': 'f'*32}

    def prepare(self, **overrides):
        arguments = dict(slot=1, sector='sector_a', grant=self.grant, timeout=2, ticket=self.ticket)
        arguments.update(overrides)
        return self.participant.prepare_fixture_player_source(self.case, self.profile, **arguments)

    def test_private_socket_installer_worker_configuration_and_redaction(self):
        candidates = [self.participant.lease, 'c'*32, '3'*32, '3'*32, '4'*32, '5'*32,
                      '5'*16+'6'*16, '6'*32]
        with patch.object(client.secrets, 'token_hex', side_effect=candidates):
            paths = self.prepare()
        self.assertTrue(all(path.is_file() for path in paths))
        owned = self.participant.motion_sock
        self.assertEqual(owned.getsockname()[0], '127.0.0.1')
        self.assertTrue(self.participant._check_motion_socket())
        config = self.participant.client_authority_worker_config
        self.assertEqual((config['lease'], config['attempt'], config['fixture_slot'], config['timeout']),
                         ('3'*32, '4'*32, 1, 2))
        self.assertEqual(config['grant'], self.grant)
        self.grant['index'] = 4
        self.assertEqual(config['grant']['index'], 3)
        installation = self.participant.fixture_source_installation
        values = tuple(installation.secrets.values())
        self.assertEqual(len(set(values)), 6)
        self.assertNotEqual(installation.secrets['bootstrap_nonce'][:16],
                            installation.secrets['sampler_nonce'][:16])
        with patch.object(client.combined.RecoveredRemoteParticipant, 'redact'):
            self.participant.redact()
        redacted = (self.ui / 'config.lua').read_text()
        self.assertTrue(all(installer.lua_literal(token) not in redacted for token in values))
        self.assertIsNone(self.participant.client_authority_worker_config)

    def test_latest_cache_is_explicit_and_installed_in_protected_overlay(self):
        paths = self.prepare(latest_cache=True)
        module = self.ui / 'fixture_player_latest_cache.lua'
        self.assertIn(module, paths)
        self.assertTrue(module.is_file())
        self.assertIn('latest_cache=true', (self.ui / 'config.lua').read_text())
        manifest = (self.ui.parent / 'ui.xml').read_text()
        self.assertIn('ui/fixture_player_latest_cache.lua', manifest)
        with patch.object(client.combined.RecoveredRemoteParticipant, 'redact'):
            self.participant.redact()
        self.assertEqual((self.ui / 'config.lua').read_text().count(installer.lua_literal('redacted')), 6)

    def test_invalid_grants_slots_and_conflicting_motion_are_rejected_before_binding(self):
        cases = [dict(slot=2), dict(sector='sector_b'), dict(timeout=True), dict(latest_cache=1),
                 dict(grant={**self.grant, 'session_epoch': '0'*32}),
                 dict(grant={**self.grant, 'epoch': self.ticket['attempt_id']})]
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.prepare(**arguments)
            self.assertIsNone(self.participant.motion_sock)
        self.participant.motion_worker_config = {'enabled': True}
        with self.assertRaises(ValueError): self.prepare()
        self.participant.motion_worker_config = None

    def test_opt_in_throttle_is_protected_one_shot_and_redacted(self):
        paths = self.prepare(throttle=True)
        for name in ('authority_fixture_client_throttle.lua', 'authority_fixture_client_throttle_driver.lua'):
            self.assertIn(self.ui / name, paths)
        self.assertIn(self.ui.parent / 'md/authority_fixture_client_throttle.xml', paths)
        installation = self.participant.fixture_source_installation
        self.assertEqual(len(installation.secrets), 9)
        self.assertIn('throttle_enabled=true', (self.ui / 'config.lua').read_text())
        config = dict(self.participant.fixture_throttle_config)
        self.participant._fixture_throttle_process = {'pid':1}
        import authority_fixture_client_throttle_ipc as ipc
        with patch.object(ipc, 'pulse', return_value={'stop_acknowledged': True}) as invoke:
            result = self.participant.pulse_fixture_throttle(process={'pid':1}, guard=lambda:True,
                running=lambda:True, pump=lambda:None)
            self.assertTrue(result['stop_acknowledged'])
            self.assertEqual(invoke.call_args.kwargs['nonce'], config['nonce'])
            with self.assertRaises(ValueError):
                self.participant.pulse_fixture_throttle(process={'pid':1}, guard=lambda:True,
                    running=lambda:True, pump=lambda:None)
        with patch.object(client.combined.RecoveredRemoteParticipant, 'redact'):
            self.participant.redact()
        self.assertTrue(all(installer.lua_literal(value) not in (self.ui/'config.lua').read_text()
                            for value in installation.secrets.values()))
        self.assertTrue(self.participant.cleanup_diagnostic())
        self.assertIsNone(self.participant.fixture_throttle_socket)

    def test_failed_throttle_fences_participant_without_retry(self):
        self.prepare(throttle=True)
        self.participant._fixture_throttle_process = {'pid':1}
        import authority_fixture_client_throttle_ipc as ipc
        with patch.object(ipc, 'pulse', side_effect=ipc.ThrottleUnconfirmed(
                'lost receipt', attempted=True, started=False, stopped=False)):
            with self.assertRaises(ipc.ThrottleUnconfirmed):
                self.participant.pulse_fixture_throttle(process={'pid':1}, guard=lambda:True,
                    running=lambda:True, pump=lambda:None)
        self.assertTrue(self.participant.fault)
        with self.assertRaises(ValueError):
            self.participant.pulse_fixture_throttle(process={'pid':1}, guard=lambda:True,
                running=lambda:True, pump=lambda:None)

    def test_throttle_socket_replacement_never_closes_foreign_socket(self):
        self.prepare(throttle=True)
        owned=self.participant.fixture_throttle_socket
        foreign=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            self.participant.fixture_throttle_socket=foreign
            with self.assertRaisesRegex(RuntimeError, 'cleanup unconfirmed'):
                self.participant.cleanup_diagnostic()
            self.assertGreaterEqual(foreign.fileno(),0)
        finally:
            self.participant.fixture_throttle_socket=owned
            self.participant.cleanup_diagnostic()
            foreign.close()

    def test_replaced_source_socket_is_not_closed_by_cleanup(self):
        self.prepare()
        owned = self.participant.motion_sock
        foreign = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.participant.motion_sock = foreign
            with self.assertRaisesRegex(RuntimeError, 'cleanup unconfirmed'):
                self.participant.cleanup_diagnostic()
            self.assertGreaterEqual(foreign.fileno(), 0)
        finally:
            self.participant.motion_sock = owned
            self.participant.cleanup_diagnostic()
            foreign.close()


if __name__ == '__main__':
    unittest.main()
