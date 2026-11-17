"""Participant worker fixture source checks; no X4 instance is started."""
import copy
import json
from pathlib import Path
import socket
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev'), str(ROOT / 'tests')]
from authority.experimental_client_load import HonestClientLoadClaim
from authority.load_messages import Receipt
from authority.trusted_load_messages import encode_load_claim
from test_authority_tcp_native_worker import identity
import authority_tcp_native_worker as worker


def configuration():
    epoch, attempt = 'a' * 32, 'c' * 32
    receipt = Receipt(epoch, 1, 1, 1, attempt, 'checkpoint-' + 'd' * 32, 'e' * 64, 10)
    grant = dict(session_epoch=epoch, epoch='1' * 32, generation='2' * 32,
                 index=3, sector_macro='sector_a', token='3' * 32, incarnation='4' * 32)
    return dict(version=1, claim=encode_load_claim(HonestClientLoadClaim(receipt, 'f' * 32, True, True)).decode(),
                epoch=epoch, handle=1, lease='b' * 32, udp_peer=['127.0.0.1', 1234], udp_next_id=1,
                deadline=time.monotonic() + 20, controller_timeout=8, client_process=identity(),
                client_authority=dict(lease='5' * 32, attempt='6' * 32, grant=grant, fixture_slot=1, timeout=1))


class ClientAuthorityWorker(unittest.TestCase):
    def test_configuration_fences_slot_session_and_distinct_secrets(self):
        original = configuration()
        self.assertEqual(worker.config_value(json.dumps(original).encode())[0], original)
        variants = []
        for path, value in ((('fixture_slot',), 2), (('fixture_slot',), True),
                            (('grant', 'session_epoch'), '0' * 32),
                            (('grant', 'index'), 4), (('lease',), original['lease']),
                            (('attempt',), 'c' * 32), (('timeout',), 2)):
            bad = copy.deepcopy(original)
            target = bad['client_authority']
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            variants.append(bad)
        conflicting = copy.deepcopy(original)
        conflicting['motion'] = {}
        variants.append(conflicting)
        for bad in variants:
            with self.subTest(configuration=bad), self.assertRaises(ValueError):
                worker.config_value(json.dumps(bad).encode())

    def test_freeze_failure_blocks_engine_pause_and_resume_failure_blocks_sampling(self):
        config = configuration()
        config['client_authority']['freeze_drain'] = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', 0))
        self.addCleanup(sock.close)
        source = worker.LazyClientAuthority(sock, config, lambda: None)
        operations = []

        class UncertainBridge:
            def freeze(self):
                operations.append('freeze')
                raise RuntimeError('freeze acknowledgement lost')
            def resume(self):
                operations.append('resume')
                raise RuntimeError('resume acknowledgement lost')

        source.bridge = UncertainBridge()
        source.running = True
        participant = worker.GuardedParticipant.__new__(worker.GuardedParticipant)
        participant.motion_gate = source
        participant.call = lambda operation, handles: operations.append(operation) or True
        with self.assertRaisesRegex(RuntimeError, 'freeze acknowledgement lost'):
            participant.pause([1])
        self.assertEqual(operations, ['freeze'])
        self.assertFalse(source.running)
        with self.assertRaisesRegex(RuntimeError, 'resume acknowledgement lost'):
            participant.resume([1])
        self.assertEqual(operations, ['freeze', 'resume', 'resume'])
        self.assertFalse(source.running)

    def test_binding_is_lazy_and_pausing_keeps_the_source_for_resume(self):
        cfg = configuration()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', 0))
        self.addCleanup(sock.close)
        source = worker.LazyClientAuthority(sock, cfg, lambda: None)
        calls = []

        class Bridge:
            state = 'new'
            def register_saved(self): self.state = 'ready'; calls.append('register'); return True
            def pull(self): calls.append('pull'); return {'sequence': len(calls)}
            def close(self): self.state = 'closed'; calls.append('close')

        def bind(passed_sock, **kwargs):
            self.assertIs(passed_sock, sock)
            self.assertEqual((kwargs['fixture_slot'], kwargs['fixture_sector'], kwargs['include_orientation']),
                             (1, 'sector_a', True))
            self.assertEqual(kwargs['expected_peer'], ('127.0.0.1', 12345))
            self.assertTrue(kwargs['guard']() and kwargs['running']())
            grant = cfg['client_authority']['grant']
            self.assertTrue(kwargs['grant'](grant['epoch'], grant['generation'], grant['index'],
                                            grant['token'], grant['incarnation'], grant['session_epoch']))
            self.assertFalse(kwargs['grant'](grant['epoch'], grant['generation'], 4,
                                             grant['token'], grant['incarnation'], grant['session_epoch']))
            calls.append('bind')
            return Bridge()

        def arm(passed_sock, **kwargs):
            self.assertIs(passed_sock, sock)
            self.assertTrue(kwargs['guard']() and kwargs['running']())
            calls.append('arm')
            return ('127.0.0.1', 12345)

        with patch('authority_client_authority_bind.bind_client_authority', side_effect=bind), \
                patch('authority_fixture_player_source_arm.arm_fixture_source', side_effect=arm):
            with self.assertRaises(RuntimeError): source.pull()
            source.running = True
            source.pull()
            source.suspend()
            with self.assertRaises(RuntimeError): source.pull()
            source.running = True
            source.pull()
            source.close()
        self.assertEqual(calls, ['arm', 'bind', 'register', 'pull', 'pull', 'close'])


if __name__ == '__main__':
    unittest.main()
