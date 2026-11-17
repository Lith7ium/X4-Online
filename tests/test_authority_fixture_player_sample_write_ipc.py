"""Real local UDP with a simulated X4 peer; no game or profile is started."""
import copy
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.experimental_tcp_motion import motion_digest
import authority_fixture_player_sample_write_ipc as subject


class FixturePlayerSampleWrite(unittest.TestCase):
    def setUp(self):
        self._make_socket_pair()

    def _make_socket_pair(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.peer.bind(('127.0.0.1', 0))
        self.peer.connect(self.sock.getsockname())
        self.peer.settimeout(.3)
        self.addCleanup(self.sock.close)
        self.addCleanup(self.peer.close)
        self.check_process = patch.object(subject, 'check_process').start()
        self.socket_owner = patch.object(subject, 'socket_owner', return_value=True).start()
        self.addCleanup(patch.stopall)
        self.lease, self.attempt = '1'*32, '2'*32
        self.grant = {'session_epoch': 'session', 'epoch': '3'*32, 'generation': '4'*32,
                      'index': 3, 'sector_macro': 'sector_a', 'token': '5'*32, 'incarnation': '6'*32}
        self.process = {'pid': 123, 'start_ticks': 4, 'exe_dev': 5, 'exe_ino': 6}
        self.live, self.granted = True, True
        self.sent = []
        self.errors = []
        self.threads = []

    def owner(self):
        instance = subject.FixturePlayerSampleWriteIPC(self.sock, enabled=True,
            lease=self.lease, attempt=self.attempt, grant=self.grant, process=self.process,
            guard=lambda: self.live, grant_guard=lambda grant: self.granted and grant == self.grant,
            timeout=.2)
        self.addCleanup(instance.close)
        return instance

    def sample(self):
        return {'version': 2, 'epoch': self.grant['epoch'], 'generation': self.grant['generation'],
                'index': self.grant['index'], 'sequence': 7, 'sector_macro': self.grant['sector_macro'],
                'source_time': 12.25, 'x': 10., 'y': -20., 'z': 30.,
                'velocity': {'x': 1., 'y': 2., 'z': 3.},
                'orientation': {'yaw': .1, 'pitch': .2, 'roll': .3},
                'angular_rate': {'yaw': .01, 'pitch': .02, 'roll': .03}}

    def ready(self, *, malformed=False):
        fields = ['R', self.lease, self.attempt, 'READY', self.grant['epoch'], self.grant['generation'],
                  str(self.grant['index']), self.grant['sector_macro']]
        if malformed:
            fields[6] = '4'
        self.peer.send('|'.join(fields).encode('ascii'))

    def responder(self, mode='ok'):
        def run():
            try:
                request = self.peer.recv(769).decode('ascii').split('|')
                self.sent.append(request)
                if mode == 'timeout':
                    return
                if mode == 'guard_loss':
                    self.live = False
                prefix = ['R', *request[1:3], 'RESULT', *request[4:11]]
                target = [float(value) for value in request[11:14]]
                if mode == 'bad_digest':
                    prefix[10] = 'f'*64
                if mode == 'bad_request':
                    prefix[4] = 'f'*32
                after = [target[0] + (.6 if mode == 'bad_position' else .25), target[1], target[2]]
                before = target if mode == 'no_displacement' else ([1000., 0., 0.] if mode == 'too_far' else [1., 2., 3.])
                fields = prefix + [format(value, '.17g') for value in before + after]
                if mode == 'nonfinite':
                    fields[-1] = '1e999'
                packet = '|'.join(fields).encode('ascii')
                self.peer.send(packet)
                if mode == 'duplicate':
                    self.peer.send(packet)
            except BaseException as error:
                self.errors.append(error)
        thread = threading.Thread(target=run)
        thread.start()
        self.threads.append(thread)
        self.addCleanup(thread.join, 1)
        return thread

    def test_each_slot_uses_exact_sample_digest_and_one_correlated_write(self):
        for index in (3, 4):
            with self.subTest(index=index):
                if index == 4:
                    self._make_socket_pair()
                self.grant['index'] = index
                sample = self.sample()
                expected = motion_digest(sample)
                owner = self.owner()
                self.ready()
                self.assertTrue(owner.wait_ready())
                thread = self.responder()
                result = owner.apply_once(sample)
                thread.join(1)
                self.assertEqual(self.errors, [])
                self.assertTrue(owner.write_attempted and owner.write_confirmed)
                self.assertEqual(owner.state, 'done')
                self.assertEqual(result['sample_sha256'], expected)
                self.assertEqual(result['registry_index'], index)
                self.assertEqual(result['before'], [1., 2., 3.])
                self.assertEqual(result['after'], [10.25, -20., 30.])
                self.assertEqual(result['target_error'], .25)
                self.assertGreaterEqual(result['initial_distance'], 1)
                self.assertLessEqual(result['initial_distance'], 50)
                self.assertTrue(result['position_only'])
                self.assertFalse(result['sustained_motion_proven'])
                self.assertEqual(self.sent[0][10], expected)
                self.assertEqual(self.sent[0][11:], ['10', '-20', '30'])
                with self.assertRaises(RuntimeError):
                    owner.apply_once(sample)
                self.assertEqual(len(self.sent), 1)

    def test_foreign_ready_or_peer_owner_is_rejected_before_dispatch(self):
        for mode in ('foreign', 'owner'):
            with self.subTest(mode=mode):
                if mode == 'owner':
                    self._make_socket_pair()
                owner = self.owner()
                self.ready(malformed=mode == 'foreign')
                if mode == 'owner':
                    self.socket_owner.return_value = False
                with self.assertRaises((RuntimeError, ValueError)):
                    owner.wait_ready()
                self.assertEqual(owner.state, 'failed')
                self.assertFalse(owner.write_attempted)
                with self.assertRaises(socket.timeout):
                    self.peer.recv(769)

    def test_bad_result_or_lost_ack_is_uncertain_and_never_retried(self):
        for mode in ('bad_digest', 'bad_request', 'bad_position', 'nonfinite', 'timeout', 'guard_loss', 'no_displacement', 'too_far'):
            with self.subTest(mode=mode):
                if mode != 'bad_digest':
                    self._make_socket_pair()
                owner = self.owner()
                self.ready(); owner.wait_ready()
                thread = self.responder(mode)
                with self.assertRaises((ValueError, RuntimeError, OSError)):
                    owner.apply_once(self.sample())
                thread.join(1)
                self.assertTrue(owner.write_attempted)
                self.assertFalse(owner.write_confirmed)
                self.assertEqual(owner.state, 'failed')
                with self.assertRaises(RuntimeError):
                    owner.apply_once(self.sample())
                self.assertEqual(len(self.sent), 1)
                self.assertEqual(self.errors, [])

    def test_foreign_sample_and_revoked_grant_cannot_dispatch(self):
        for mode in ('foreign', 'revoked'):
            with self.subTest(mode=mode):
                if mode == 'revoked':
                    self._make_socket_pair()
                owner = self.owner()
                self.ready(); owner.wait_ready()
                sample = self.sample()
                if mode == 'foreign':
                    sample['index'] = 4
                else:
                    self.granted = False
                with self.assertRaises((ValueError, RuntimeError)):
                    owner.apply_once(sample)
                self.assertFalse(owner.write_attempted)
                with self.assertRaises(socket.timeout):
                    self.peer.recv(769)

    def test_unexpected_queued_packet_blocks_write(self):
        owner = self.owner()
        self.ready(); owner.wait_ready()
        self.peer.send(b'unexpected')
        with self.assertRaisesRegex(RuntimeError, 'queued'):
            owner.apply_once(self.sample())
        self.assertFalse(owner.write_attempted)
        self.assertEqual(owner.state, 'failed')
        with self.assertRaises(socket.timeout):
            self.peer.recv(769)

    def test_guard_numeric_type_change_or_reentry_fences_write(self):
        for mode in ('numeric_type', 'reentry'):
            with self.subTest(mode=mode):
                if mode == 'reentry':
                    self._make_socket_pair()
                owner = self.owner()
                self.ready(); owner.wait_ready()
                def probe(candidate):
                    if mode == 'numeric_type':
                        candidate['index'] = 3.0
                    else:
                        try:
                            owner.apply_once(self.sample())
                        except RuntimeError:
                            pass
                    return True
                owner._grant_guard = probe
                with self.assertRaises((RuntimeError, OSError)):
                    owner.apply_once(self.sample())
                self.assertFalse(owner.write_attempted)
                self.assertEqual(owner.state, 'failed')
                with self.assertRaises(socket.timeout):
                    self.peer.recv(769)

    def test_duplicate_udp_owner_and_grant_mutation_are_fenced(self):
        owner = self.owner()
        with self.assertRaisesRegex(ValueError, 'already owned'):
            self.owner()
        self.ready(); owner.wait_ready()
        original = copy.deepcopy(self.grant)
        def mutate(candidate):
            candidate['index'] = 4
            return True
        owner._grant_guard = mutate
        with self.assertRaisesRegex(RuntimeError, 'grant guard'):
            owner.apply_once(self.sample())
        self.assertEqual(self.grant, original)
        self.assertFalse(owner.write_attempted)


if __name__ == '__main__':
    unittest.main()
