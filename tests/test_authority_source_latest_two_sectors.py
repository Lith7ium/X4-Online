"""Two synthetic sectors over the existing latest-motion TCP/UDP owners.

The selector is an explicit test input, not X4 visibility or map discovery.
No X4 process, native object binding, Internet, or Windows client is involved.
"""
import json
import socket
import threading
import time
import unittest

from tests import test_authority_experimental_tcp_motion as fixture
from tests import test_authority_experimental_tcp_participants as participant_fixture
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion, motion_digest
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient

TEST_TIMEOUT = 10
PEER_TIMEOUT = 30
SOURCE_TIMEOUT = 45
POLL_INTERVAL = .005
MOTION_INTERVAL = 1 / 240
EPOCH = 'b' * 32
GENERATION = 'c' * 32
SECTOR_A_TRACK = 10055
SECTOR_B_TRACK = 10056


class SourceLatestTwoSectors(unittest.TestCase):
    def setUp(self):
        # Reuse the fixture methods on this running TestCase so their public
        # addCleanup calls are reported by the normal unittest result.
        participant_fixture.ParticipantTCPTest.setUp(self)
        self.stop = threading.Event()
        self.threads = []
        self.errors = []
        self.received = []
        self.expected_disconnect = set()
        self.release_slow_receipt = threading.Event()
        first = participant_fixture.ParticipantTCPTest.connect(self)
        second = participant_fixture.ParticipantTCPTest.connect(self)
        self.addCleanup(fixture.MotionTCP.finish, self)
        self.addCleanup(self.release_slow_receipt.set)
        participant_fixture.ParticipantTCPTest.offer_and_claim(self, first)
        participant_fixture.ParticipantTCPTest.offer_and_claim(self, second)
        fixture.MotionTCP.client(self, first, 1)
        self.start_slow_participant(second)
        self.host.tick(.1)
        self.control.enable_latest_motion(enabled=True, timeout=PEER_TIMEOUT)
        self.delivery = ExperimentalTCPJobDelivery(self.host, enabled=True, timeout=PEER_TIMEOUT)
        self.motion = ExperimentalTCPMotion(self.delivery, enabled=True, min_interval=MOTION_INTERVAL)

        local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        remote = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(local.close)
        self.addCleanup(remote.close)
        local.bind(('127.0.0.1', 0))
        remote.bind(('127.0.0.1', 0))
        local.connect(remote.getsockname())
        remote.connect(local.getsockname())
        remote.settimeout(TEST_TIMEOUT)
        self.remote = remote
        members = self.delivery.membership()
        self.recipients = {'sector_a': members[0], 'sector_b': members[1]}

        def select_recipients(sample, _members):
            return [dict(self.recipients[sample['sector_macro']])]

        self.bridge = ExperimentalSourceMotionIPC(
            local, self.motion, enabled=True, lease='1' * 32, attempt='2' * 32,
            epoch=EPOCH, generation=GENERATION, guard=lambda: True,
            validate_peer=lambda peer: peer == remote.getsockname(), timeout=SOURCE_TIMEOUT,
            select_recipients=select_recipients, latest=True,
            saved_baseline=20000, saved_guard=lambda epoch, count: epoch == EPOCH and count == 20000,
            saved_lifetime_guard=lambda epoch, count: epoch == EPOCH and count == 20000,
        )
        self.bridge.bind_confirmed(SECTOR_A_TRACK)
        self.bridge.bind_confirmed(SECTOR_B_TRACK)

    def start_slow_participant(self, connection):
        """Hold the actual participant callback until the test releases it."""
        def run():
            try:
                connection.settimeout(PEER_TIMEOUT)
                frame = b''
                while not frame.endswith(b'\n'):
                    part = connection.recv(1)
                    if not part:
                        raise RuntimeError('missing admission')
                    frame += part
                if json.loads(frame)['kind'] != 'accepted':
                    raise RuntimeError('unexpected admission')

                def accept(sample, despawn):
                    self.received.append((2, dict(sample), despawn))
                    return self.release_slow_receipt.wait(PEER_TIMEOUT)

                participant = ExperimentalTCPParticipantClient(
                    connection, fixture.Controller(), enabled=True, epoch='a' * 32,
                    handle=2, timeout=PEER_TIMEOUT, apply_motion=accept, apply_job=lambda _: True,
                )
                while not self.stop.is_set():
                    participant.poll(.05)
                participant.close()
            except BaseException as error:
                if not self.stop.is_set() and 2 not in self.expected_disconnect:
                    self.errors.append(error)

        thread = threading.Thread(target=run)
        self.threads.append(thread)
        thread.start()

    def wait_for(self, predicate, timeout=TEST_TIMEOUT):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.host.tick(POLL_INTERVAL)
        self.assertTrue(predicate())

    def sample(self, index, sequence, sector, velocity):
        # The bridge rate limit is independent of the synthetic source clock.
        time.sleep(MOTION_INTERVAL + .001)
        self.assertTrue(self.bridge.begin_latest())
        request = self.remote.recv(769).decode('ascii').split('|')
        self.assertEqual(request[:6], ['P', '1' * 32, '2' * 32, 'PULL', EPOCH, GENERATION])
        self.assertEqual(len(request), 7)
        self.assertTrue(request[6].isdigit() and int(request[6]) > 0)
        response = [
            'S', '1' * 32, '2' * 32, 'SAMPLE', EPOCH, GENERATION,
            request[-1], str(index), str(sequence), sector, str(sequence),
            '1', '2', '3', *velocity,
        ]
        self.remote.send('|'.join(response).encode('ascii'))
        complete, sample = self.bridge.poll_latest()
        self.assertTrue(complete)
        return sample

    def test_sector_selection_slow_peer_and_replaced_incarnation(self):
        original_second = dict(self.recipients['sector_b'])
        slow = self.sample(SECTOR_B_TRACK, 1, 'sector_b', ['-', '-', '-'])
        self.assertIsNone(slow['velocity'])
        self.wait_for(lambda: any(handle == 2 for handle, _, _ in self.received))

        fast = self.sample(SECTOR_A_TRACK, 1, 'sector_a', ['10', '0', '0'])
        self.assertEqual(fast['velocity'], {'x': 10.0, 'y': 0.0, 'z': 0.0})
        fast_track = self.motion._tracks[(EPOCH, GENERATION, SECTOR_A_TRACK)]
        fast_member = self.recipients['sector_a']
        fast_identity = (fast_member['id'], fast_member['incarnation'])
        expected_fast_receipt = (fast['sequence'], motion_digest(fast))
        self.wait_for(lambda: fast_track['peer_samples'].get(fast_identity) == expected_fast_receipt)
        slow_track = self.motion._tracks[(EPOCH, GENERATION, SECTOR_B_TRACK)]
        slow_identity = (original_second['id'], original_second['incarnation'])
        self.assertNotIn(slow_identity, slow_track['peer_samples'])
        self.release_slow_receipt.set()
        self.wait_for(self.control._motion_idle)
        self.assertEqual([(handle, sample['sector_macro']) for handle, sample, _ in self.received],
                         [(2, 'sector_b'), (1, 'sector_a')])

        self.expected_disconnect.add(2)
        old_socket = next(conn for conn, peer in self.control._peers.items() if peer['handle'] == 2)
        self.control._drop(old_socket)
        replacement = participant_fixture.ParticipantTCPTest.connect(self)
        # Mark teardown before closing this socket; thread joining follows later.
        self.addCleanup(self.stop.set)
        self.host.tick(.1)
        participant_fixture.ParticipantTCPTest.offer_and_claim(self, replacement)
        fixture.MotionTCP.client(self, replacement, 3)
        self.host.tick(.1)
        # A subsequent host tick releases the world lifecycle barrier.
        self.host.tick(0)
        self.recipients['sector_b'] = self.delivery.membership()[1]
        self.assertNotEqual(self.recipients['sector_b']['incarnation'], original_second['incarnation'])

        self.sample(SECTOR_B_TRACK, 2, 'sector_b', ['-', '-', '-'])
        self.wait_for(lambda: any(handle == 3 for handle, _, _ in self.received))
        self.wait_for(self.control._motion_idle)
        self.assertNotIn(slow_identity, slow_track['peer_samples'])

        # Even with the new member ID, its predecessor's incarnation is stale.
        self.recipients['sector_b'] = {
            'id': self.recipients['sector_b']['id'],
            'incarnation': original_second['incarnation'],
        }
        with self.assertRaises(ValueError):
            self.sample(SECTOR_B_TRACK, 3, 'sector_b', ['-', '-', '-'])
        self.assertEqual([sample['sequence'] for handle, sample, _ in self.received if handle == 3], [2])


if __name__ == '__main__':
    unittest.main()
