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
    allow_sector_reentry = False

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
        self.motion = ExperimentalTCPMotion(self.delivery, enabled=True, min_interval=MOTION_INTERVAL,
                                            allow_sector_reentry=self.allow_sector_reentry)

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
            member = self.recipients.get(sample['sector_macro'])
            return [dict(member)] if member is not None else []

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


class SourceLatestReentry(unittest.TestCase):
    allow_sector_reentry = True
    setUp = SourceLatestTwoSectors.setUp
    wait_for = SourceLatestTwoSectors.wait_for
    sample = SourceLatestTwoSectors.sample

    def start_slow_participant(self, connection):
        # Synthetic peer for the actual TCP wire. A separate client test owns
        # the engine-binding callbacks and exactly-once write behavior.
        self.frames = []
        self.prepare_received = threading.Event()
        self.align_received = threading.Event()
        self.release_align = threading.Event()
        self.addCleanup(self.release_align.set)

        def stop_reader():
            self.stop.set()
            connection.shutdown(socket.SHUT_RDWR)

        self.addCleanup(stop_reader)

        def run():
            try:
                connection.settimeout(PEER_TIMEOUT)
                reader = connection.makefile('rb')
                if json.loads(reader.readline())['kind'] != 'accepted':
                    raise RuntimeError('unexpected admission')
                while not self.stop.is_set():
                    line = reader.readline()
                    if not line:
                        break
                    command = json.loads(line)
                    kind = command['kind']
                    if kind == 'participant_command':
                        receipt = dict(command, kind='participant_receipt', status='confirmed')
                        connection.sendall(json.dumps(receipt).encode() + b'\n')
                        continue
                    self.frames.append(command)
                    receipt = {k: v for k, v in command.items() if k not in ('kind', 'sample')}
                    if kind == 'motion_snapshot':
                        status = 'accepted'
                        receipt_kind = 'motion_receipt'
                    elif kind == 'motion_reentry_prepare':
                        self.prepare_received.set()
                        if not self.release_slow_receipt.wait(PEER_TIMEOUT):
                            raise TimeoutError('test did not release prepare')
                        status, receipt_kind = 'prepared', 'motion_reentry_prepared_receipt'
                    elif kind == 'motion_reentry_align':
                        self.align_received.set()
                        if not self.release_align.wait(PEER_TIMEOUT):
                            raise TimeoutError('test did not release align')
                        status, receipt_kind = 'aligned', 'motion_reentry_aligned_receipt'
                    elif kind == 'motion_reentry_cancel':
                        status, receipt_kind = 'canceled', 'motion_reentry_canceled_receipt'
                    else:
                        raise ValueError(kind)
                    if 'sample' in command:
                        receipt['sample_sha256'] = motion_digest(command['sample'])
                    receipt.update(kind=receipt_kind, status=status)
                    connection.sendall(json.dumps(receipt).encode() + b'\n')
            except BaseException as error:
                if not self.stop.is_set():
                    self.errors.append(error)

        thread = threading.Thread(target=run)
        self.threads.append(thread)
        thread.start()

    def begin_v3(self):
        time.sleep(MOTION_INTERVAL + .001)
        self.assertTrue(self.bridge.begin_latest())
        return self.remote.recv(769).decode('ascii').split('|')[-1]

    def finish_v3(self, request, sequence, sector, rate):
        self.remote.send('|'.join([
            'S', '1' * 32, '2' * 32, 'SAMPLE3', EPOCH, GENERATION,
            request, str(SECTOR_B_TRACK), str(sequence), sector, '14', str(sequence + 40),
            str(sequence * 25), '2', '3', *rate,
        ]).encode('ascii'))
        complete, value = self.bridge.poll_latest()
        self.assertTrue(complete)
        return value

    def request_v3(self, sequence, sector, rate=('-', '-', '-')):
        return self.finish_v3(self.begin_v3(), sequence, sector, rate)

    def begin_return(self, *, other_interested=False):
        old = self.request_v3(1, 'sector_b')
        peer = self.recipients['sector_b']
        self.identity = (peer['id'], peer['incarnation'])
        self.track = self.motion._tracks[(EPOCH, GENERATION, SECTOR_B_TRACK)]
        self.wait_for(lambda: self.track['peer_samples'].get(self.identity) == (1, motion_digest(old)))
        # The real source selector excludes the returning peer, regardless of
        # whether another participant was watching the destination.
        if other_interested:
            self.recipients['sector_c'] = self.recipients['sector_a']
        absent_sample = self.request_v3(2, 'sector_c')
        self.assertEqual(absent_sample is not None, other_interested)
        self.recipients['sector_c'] = peer
        self.request_v3(3, 'sector_c', ('12', '0', '0'))
        self.wait_for(self.prepare_received.is_set)
        self.assertEqual(self.track['peer_frames'][self.identity], 'sector_b')
        prepared = self.frames[-1]
        self.assertEqual(prepared['kind'], 'motion_reentry_prepare')
        self.assertEqual(prepared['previous_sector'], 'sector_b')
        self.assertEqual(prepared['sample']['version'], 3)
        self.assertIsNone(prepared['sample']['real_velocity'])
        return prepared

    def test_align_uses_confirmed_later_pull_while_other_peer_moves(self):
        prepared = self.begin_return(other_interested=True)
        self.sample(SECTOR_A_TRACK, 1, 'sector_a', ['-', '-', '-'])
        self.wait_for(lambda: any(handle == 1 and sample['index'] == SECTOR_A_TRACK
                                  for handle, sample, _ in self.received))
        earlier_request = self.begin_v3()
        self.release_slow_receipt.set()
        self.wait_for(lambda: self.track['reentries'][self.identity]['phase'] == 'prepared')
        self.finish_v3(earlier_request, 4, 'sector_c', ('17', '0', '0'))
        for _ in range(5):
            self.host.tick(POLL_INTERVAL)
        self.assertFalse(self.align_received.is_set())

        fresh = self.request_v3(5, 'sector_c', ('32', '0', '0'))
        self.wait_for(self.align_received.is_set)
        alignment = self.frames[-1]
        self.assertEqual(alignment['sample'], fresh)
        self.assertEqual(alignment['prepared_sequence'], prepared['request_id'])
        self.assertEqual(self.track['peer_frames'][self.identity], 'sector_b')
        self.assertEqual(self.track['peer_samples'][self.identity][0], 1)
        self.release_align.set()
        self.wait_for(lambda: self.track['peer_samples'].get(self.identity) == (5, motion_digest(fresh)))
        self.request_v3(6, 'sector_c', ('33', '0', '0'))
        self.wait_for(self.control._motion_idle)
        self.assertEqual(self.frames[-1]['kind'], 'motion_snapshot')
        self.assertEqual(self.track['peer_frames'][self.identity], 'sector_c')

    def test_interest_loss_during_prepare_cancels_without_disconnect_or_write(self):
        prepared = self.begin_return()
        del self.recipients['sector_c']
        self.assertIsNone(self.request_v3(4, 'sector_c'))
        self.release_slow_receipt.set()
        self.wait_for(self.control._motion_idle)
        self.assertFalse(self.align_received.is_set())
        canceled = self.frames[-1]
        self.assertEqual(canceled['kind'], 'motion_reentry_cancel')
        self.assertEqual(canceled['request_id'], prepared['request_id'])
        self.assertEqual(canceled['prepared_sequence'], prepared['request_id'])
        self.assertEqual(canceled['sample_sha256'], motion_digest(prepared['sample']))
        self.assertEqual(self.delivery.membership()[1], self.recipients['sector_b'])
        self.assertEqual(self.track['peer_frames'][self.identity], 'sector_b')
        self.assertEqual(self.track['peer_samples'][self.identity][0], 1)

    def test_changed_frame_without_positive_absence_is_rejected(self):
        old = self.request_v3(1, 'sector_b')
        peer = self.recipients['sector_b']
        identity = (peer['id'], peer['incarnation'])
        track = self.motion._tracks[(EPOCH, GENERATION, SECTOR_B_TRACK)]
        self.wait_for(lambda: track['peer_samples'].get(identity) == (1, motion_digest(old)))
        self.recipients['sector_c'] = peer
        with self.assertRaisesRegex(ValueError, 'recipient motion frame changed without resync'):
            self.request_v3(2, 'sector_c')
        self.assertFalse(self.prepare_received.is_set())
        self.assertEqual(track['peer_frames'][identity], 'sector_b')

    def test_lifecycle_barrier_drains_cancel_before_release(self):
        self.begin_return()
        self.release_slow_receipt.set()
        self.wait_for(lambda: self.track['reentries'][self.identity]['phase'] == 'prepared')
        self.assertFalse(self.control.motion_barrier())
        self.assertFalse(self.bridge.begin_latest())
        self.wait_for(self.control._motion_idle)
        self.assertEqual(self.frames[-1]['kind'], 'motion_reentry_cancel')
        self.assertEqual(self.track['peer_frames'][self.identity], 'sector_b')
        self.control.release_motion_barrier()
        self.assertEqual(len(self.delivery.membership()), 2)


if __name__ == '__main__':
    unittest.main()
