"""Private recovery setter wiring, with simulated X4 and no native game."""
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev'), str(ROOT / 'tests')]
from authority.experimental_client_load import HonestClientLoadClaim
from authority.load_messages import Receipt
from authority.trusted_load_messages import encode_load_claim
import authority_recovered_server_client as client
import authority_tcp_native_worker as worker
import test_authority_recovered_client_motion_install as install_fixtures

EPOCH = '4ba7be438ebb04ec5bb85fdb95b5a488'
FIXTURE = 'recovery_enh_870'


def worker_config():
    epoch, attempt = '9' * 32, '7' * 32
    receipt = Receipt(epoch, 1, 1, 1, attempt, 'checkpoint-' + '6' * 32, '5' * 64, 10)
    return {
        'version': 1, 'claim': encode_load_claim(HonestClientLoadClaim(receipt, '4' * 32, True, True)).decode(),
        'epoch': epoch, 'handle': 1, 'lease': '8' * 32, 'udp_peer': ['127.0.0.1', 1234],
        'udp_next_id': 1, 'deadline': time.monotonic() + 5, 'controller_timeout': 3,
        'client_process': {'pid': os.getpid(), 'start_ticks': 1, 'exe_dev': 1, 'exe_ino': 1},
        'motion': {'lease': 'a' * 32, 'attempt': 'b' * 32, 'epoch': EPOCH,
                   'generation': 'd' * 32, 'timeout': 1},
    }


class SetterSetup(unittest.TestCase):
    def participant(self):
        participant = client.ServerClient(time.monotonic() + 5, Path('/unused'), keep_worker=True)
        self.addCleanup(participant.cleanup_diagnostic)
        return participant

    def test_fixture_is_explicit_and_forwarded_to_installer_and_worker(self):
        participant = self.participant()
        request = {'indices': [1318], 'generation': '3' * 32, 'timeout': 2,
                   'saved_apply_fixture': FIXTURE}
        status = ('ready', EPOCH, 10082, 'd' * 64)
        with patch('authority_recovered_client_motion_install.install', return_value=Mock(paths=())) as install:
            participant.prepare_client_motion(Path('/unused'), Path('/unused'), status, request,
                                              {'world_epoch': 'e' * 32, 'attempt_id': 'f' * 32})
        self.assertEqual(install.call_args.args[3]['saved_apply_fixture'], FIXTURE)
        self.assertEqual(install.call_args.args[3]['index'], 1318)
        self.assertNotIn('indices', install.call_args.args[3])
        self.assertEqual(participant.motion_worker_config['saved_apply_fixture'], FIXTURE)
        self.assertEqual(participant.motion_worker_config['epoch'], EPOCH)
        participant.motion_installation = None

    def test_invalid_fixture_or_identity_is_refused_before_install(self):
        status = ('ready', EPOCH, 10082, 'd' * 64)
        request = {'indices': [1318], 'generation': '3' * 32, 'timeout': 2,
                   'saved_apply_fixture': FIXTURE}
        variations = [
            ({**request, 'saved_apply_fixture': False}, status),
            ({**request, 'saved_apply_fixture': 'another'}, status),
            ({**request, 'indices': [1317]}, status),
            ({**request, 'indices': [1318, 1319]}, status),
            (request, ('ready', 'c' * 32, 10082, 'd' * 64)),
        ]
        with patch('authority_recovered_client_motion_install.install') as install:
            for bad_request, bad_status in variations:
                with self.subTest(request=bad_request, status=bad_status):
                    participant = self.participant()
                    with self.assertRaises(ValueError):
                        participant.prepare_client_motion(Path('/unused'), Path('/unused'), bad_status, bad_request,
                                                          {'world_epoch': 'e' * 32, 'attempt_id': 'f' * 32})
                    self.assertIsNone(participant.motion_sock)
            install.assert_not_called()

    def test_worker_config_is_default_off_and_fixture_is_epoch_fenced(self):
        config = worker_config()
        with patch.object(worker, 'check_process'):
            self.assertEqual(worker.config_value(json.dumps(config).encode())[0], config)
            config['motion']['saved_apply_fixture'] = FIXTURE
            self.assertEqual(worker.config_value(json.dumps(config).encode())[0], config)
            for key, bad in [('saved_apply_fixture', False), ('saved_apply_fixture', 'other'), ('epoch', 'c' * 32)]:
                altered = {**config, 'motion': {**config['motion'], key: bad}}
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    worker.config_value(json.dumps(altered).encode())


class RealInstallerWiring(unittest.TestCase):
    def setUp(self):
        install_fixtures.Install.setUp(self)

    def test_prepare_installs_fixture_into_disposable_overlay(self):
        previous = self.status
        self.status = ('ready', EPOCH, 10082, 'd' * 64)
        loader = self.ui / 'authority_download_load_probe.lua'
        text = loader.read_text()
        loader.write_text(text.replace(previous[1] + '|' + str(previous[2]), EPOCH + '|10082'))
        participant = client.ServerClient(time.monotonic() + 5, self.case, keep_worker=True)
        self.addCleanup(participant.cleanup_diagnostic)
        paths = participant.prepare_client_motion(
            self.case, self.profile, self.status,
            {'indices': [1318], 'generation': '3' * 32, 'timeout': 2, 'saved_apply_fixture': FIXTURE},
            {'world_epoch': 'e' * 32, 'attempt_id': 'f' * 32})
        self.assertTrue(all(path.is_file() for path in paths))
        config = (self.ui / 'config.lua').read_text()
        self.assertIn('authority_client_motion_index=1318', config)
        self.assertNotIn('authority_client_motion_indices=', config)
        self.assertIn('authority_client_motion_saved_apply_fixture="recovery_enh_870"', config)
        self.assertEqual(participant.motion_worker_config['saved_apply_fixture'], FIXTURE)
        participant.redact()


class LazySetter(unittest.TestCase):
    def setUp(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.addCleanup(self.sock.close)
        self.config = worker_config()
        self.config['motion']['saved_apply_fixture'] = FIXTURE
        self.owner = worker.LazyMotion(self.sock, self.config, lambda: True)
        self.owner.running = True
        self.owner.bridge = Mock()
        self.owner.bridge.preflight.return_value = 'READY'
        self.owner.bridge.apply_once.return_value = True
        self.sample = {'epoch': EPOCH, 'index': 1318, 'generation': 'd' * 32}

    def test_preflight_and_apply_use_bound_bridge(self):
        self.assertEqual(self.owner.preflight(self.sample), 'READY')
        self.assertIs(self.owner.apply_once(self.sample), True)
        self.owner.bridge.preflight.assert_called_once_with(self.sample)
        self.owner.bridge.apply_once.assert_called_once_with(self.sample)

    def test_wrong_track_and_paused_or_disabled_are_refused_before_ipc(self):
        for change in ({'epoch': 'c' * 32}, {'index': 1317}, {'index': True}, {'generation': 'e' * 32}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.owner.preflight({**self.sample, **change})
        self.owner.running = False
        with self.assertRaises(RuntimeError):
            self.owner.apply_once(self.sample)
        self.owner.running = True
        self.owner.stopped = True
        with self.assertRaises(RuntimeError):
            self.owner.apply_once(self.sample)
        self.owner.stopped = False
        del self.config['motion']['saved_apply_fixture']
        with self.assertRaises(RuntimeError):
            self.owner.preflight(self.sample)
        self.owner.bridge.preflight.assert_not_called()
        self.owner.bridge.apply_once.assert_not_called()


class LoopbackSetter(unittest.TestCase):
    def test_motion_binding_preflight_and_one_shot_over_actual_udp(self):
        local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        local.bind(('127.0.0.1', 0))
        peer.bind(('127.0.0.1', 0))
        peer.settimeout(2)
        self.addCleanup(local.close)
        self.addCleanup(peer.close)
        config = worker_config()
        config['motion']['saved_apply_fixture'] = FIXTURE
        owner = worker.LazyMotion(local, config, lambda: True)
        owner.running = True
        sample = {'version': 1, 'epoch': EPOCH, 'generation': 'd' * 32, 'index': 1318,
                  'sequence': 1, 'sector_macro': 'sector_a', 'source_time': 1,
                  'x': 1, 'y': 2, 'z': 3, 'velocity': None}
        commands, errors = [], []

        def reply_as_simulated_x4():
            try:
                peer.sendto(f"R|{'a' * 32}|{'b' * 32}|READY|{EPOCH}|{'d' * 32}".encode(), local.getsockname())
                for _ in range(3):
                    packet, address = peer.recvfrom(768)
                    fields = packet.decode('ascii').split('|')
                    commands.append(fields[3])
                    if fields[3] == 'BIND':
                        reply = ['R', *fields[1:3], 'BOUND', *fields[4:11]]
                    elif fields[3] == 'PREFLIGHT':
                        reply = ['R', *fields[1:3], 'PREFLIGHTED', *fields[4:], 'READY']
                    elif fields[3] == 'APPLY':
                        reply = ['R', *fields[1:3], 'APPLIED', *fields[4:]]
                    else:
                        raise AssertionError('unexpected IPC operation')
                    peer.sendto('|'.join(reply).encode('ascii'), address)
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=reply_as_simulated_x4)
        thread.start()
        try:
            # No real X4 process exists in this test; ownership is tested elsewhere.
            with patch('authority_tcp_job_client_live.socket_owner', return_value=True):
                self.assertIs(owner(sample, False), True)
                self.assertEqual(owner.preflight(sample), 'READY')
                self.assertIs(owner.apply_once(sample), True)
                with self.assertRaises(RuntimeError):
                    owner.apply_once(sample)
        finally:
            thread.join(3)
            owner.close()
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(commands, ['BIND', 'PREFLIGHT', 'APPLY'])


if __name__ == '__main__':
    unittest.main()
