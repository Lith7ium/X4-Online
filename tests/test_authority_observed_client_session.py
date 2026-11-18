"""Real local TCP/UDP; synthetic log, process guard and X4 participant."""
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority.experimental_client_owner import ExperimentalClientOwner
from authority.experimental_tcp_control import offer_request
from authority.load_messages import Offer
from authority.local_participant_control import LocalParticipantControl
from authority.observed_client_session import ObservedClientSession
from authority.trusted_load_messages import decode_load_claim, encode_bound_offer
from authority.trusted_marker_load_session import MarkerBoundOffer
from lockstep.launcher.joinfiles import FileService


class ObservedSessionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        content = b'isolated synthetic checkpoint'
        source = self.root / 'source'
        source.write_bytes(content)
        self.offer = Offer(world_epoch='a' * 32, connection_handle=1, baseline_id=1, load_generation=1,
            attempt_id='c' * 32, checkpoint_id='checkpoint-' + 'd' * 32,
            sha256=hashlib.sha256(content).hexdigest(), size=len(content), name='j1.xml.gz')
        self.bound = MarkerBoundOffer(self.offer, 'b' * 32)
        self.service = FileService('f' * 32, slots=(1,)).start()
        self.addCleanup(self.service.close)
        self.service.offer(self.offer.name, source)
        self.stop = threading.Event()
        self.server_done = threading.Event()
        self.errors, self.claims, self.replies, self.commands, self.keepalives = [], [], [], [], []
        self.log = b''
        self.partial_during_command = False

    def connect(self, *, disconnect=False, keepalive_interval=2):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        client = socket.create_connection(listener.getsockname(), timeout=2)
        def server():
            try:
                conn, _ = listener.accept()
                conn.settimeout(4)
                with conn, conn.makefile('rb', buffering=0) as stream:
                    if stream.readline() != offer_request():
                        raise AssertionError('unexpected offer request')
                    conn.sendall(encode_bound_offer(self.bound) + b'\n')
                    while True:
                        line = stream.readline()
                        if not line:
                            return
                        frame = json.loads(line)
                        if frame.get('kind') != 'keepalive':
                            break
                        self.keepalives.append(frame['sequence'])
                        conn.sendall(json.dumps({'version': 1, 'kind': 'alive',
                            'attempt_id': frame['attempt_id'], 'sequence': frame['sequence']}).encode() + b'\n')
                    self.claims.append(decode_load_claim(line.rstrip(b'\n')))
                    conn.sendall(json.dumps({'version': 1, 'kind': 'accepted',
                                             'attempt_id': self.offer.attempt_id}).encode() + b'\n')
                    if disconnect:
                        return
                    command = {'version': 1, 'kind': 'participant_command', 'epoch': self.offer.world_epoch,
                               'connection_handle': 1, 'request_id': 1, 'operation': 'resume'}
                    conn.sendall(json.dumps(command).encode() + b'\n')
                    reply = stream.readline()
                    if reply:
                        self.replies.append(json.loads(reply))
                    else:
                        return
                    self.stop.wait(4)
            except BaseException as error:
                self.errors.append(error)
            finally:
                self.server_done.set()
        thread = threading.Thread(target=server)
        thread.start()
        self.addCleanup(self.join_thread, thread)
        deadline = time.monotonic() + 8
        owner = ExperimentalClientOwner(client, enabled=True, file_host='127.0.0.1',
            file_port=self.service.port, file_token='f' * 32, file_slot=1,
            deadline=deadline, io_timeout=2, keepalive_interval=keepalive_interval)
        self.addCleanup(owner.close)
        bound = owner.request_offer()
        downloaded = owner.download(self.root/'download')
        slot_dir = self.root/'save'; slot_dir.mkdir()
        owner.copy_to_new_slot(downloaded, slot_dir/'save_009.xml.gz')
        return owner, client, bound, deadline

    def join_thread(self, thread):
        self.stop.set()
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.errors, [])

    def start_fake_participant(self, controller):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(('127.0.0.1', 0)); udp.settimeout(.05)
        destination = controller.sock.getsockname()
        def game():
            try:
                while not self.stop.is_set():
                    udp.sendto(('HELLO|' + controller.lease + '|' + self.offer.world_epoch).encode(), destination)
                    try:
                        data, peer = udp.recvfrom(1024)
                    except socket.timeout:
                        continue
                    fields = data.decode('ascii').split('|')
                    if len(fields) != 5 or fields[:3] != ['CMD', controller.lease, self.offer.world_epoch]:
                        raise AssertionError('unexpected participant command')
                    self.commands.append(fields[4])
                    if self.partial_during_command:
                        self.log += b'[X4LAN] AUTH_PARTICIPANT ERR'
                    udp.sendto('|'.join(('RECEIPT', *fields[1:], 'confirmed')).encode(), peer)
            except BaseException as error:
                self.errors.append(error)
            finally:
                udp.close()
        thread = threading.Thread(target=game)
        thread.start()
        self.addCleanup(self.join_thread, thread)

    def log_parts(self):
        fields = '|'.join(str(value) for value in (self.offer.world_epoch, 1, 1, 1, self.offer.checkpoint_id,
                          self.offer.sha256, self.offer.attempt_id, 'save_009')).encode()
        return (b'[X4LAN] AUTH_DOWNLOAD_LOAD load_requested|' + fields + b'\n',
                b'[X4LAN] AUTH_MARKER load INSPECTED ' + self.bound.marker.encode() + b'\n',
                b'[X4LAN] AUTH_DOWNLOAD_LOAD pause_observed|' + fields + b'\n')

    def test_real_tcp_udp_handoff_and_late_duplicate(self):
        owner, client, bound, deadline = self.connect(keepalive_interval=.02)
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        self.start_fake_participant(controller)
        request, marker, pause = self.log_parts()
        self.log = request + marker + pause[:-1]
        def complete_log():
            time.sleep(.1)
            self.log += b'\n'
        writer = threading.Thread(target=complete_log)
        writer.start(); self.addCleanup(writer.join)
        session = ObservedClientSession(owner, bound, controller, slot='save_009',
            read_log=lambda: self.log, guard=lambda: True, deadline=deadline)
        self.addCleanup(session.close)
        self.assertTrue(session.start())
        self.assertEqual(owner._participant._timeout, controller.timeout + 1)
        while not self.replies:
            session.poll(.1)
        self.assertEqual(self.replies[0]['status'], 'confirmed')
        self.assertEqual(len(self.claims), 1)
        self.assertGreater(len(self.keepalives), 0)
        self.log += request
        with self.assertRaisesRegex(ValueError, 'out of order'):
            session.poll()
        self.assertEqual(client.fileno(), -1)
        self.assertEqual(controller.sock.fileno(), -1)

    def test_wrong_ticket_rejected_before_claim(self):
        owner, client, bound, deadline = self.connect()
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        request, marker, pause = self.log_parts()
        self.log = request.replace(self.offer.attempt_id.encode(), b'e' * 32) + marker + pause
        session = ObservedClientSession(owner, bound, controller, slot='save_009',
            read_log=lambda: self.log, guard=lambda: True, deadline=deadline)
        with self.assertRaisesRegex(ValueError, 'out of order'):
            session.start()
        self.assertTrue(self.server_done.wait(2))
        self.assertEqual(client.fileno(), -1)
        self.assertEqual(controller.sock.fileno(), -1)
        self.assertEqual(self.claims, [])

    def test_disconnect_after_claim_fences_owners(self):
        owner, client, bound, deadline = self.connect(disconnect=True)
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        self.start_fake_participant(controller)
        self.log = b''.join(self.log_parts())
        session = ObservedClientSession(owner, bound, controller, slot='save_009',
            read_log=lambda: self.log, guard=lambda: True, deadline=deadline)
        self.addCleanup(session.close)
        self.assertTrue(session.start())
        with self.assertRaises((ConnectionError, RuntimeError)):
            while True:
                session.poll(.1)
        self.assertEqual(len(self.claims), 1)
        self.assertEqual(client.fileno(), -1)
        self.assertEqual(controller.sock.fileno(), -1)

    def test_partial_late_error_defers_pending_command_then_faults(self):
        owner, client, bound, deadline = self.connect()
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        self.start_fake_participant(controller)
        self.log = b''.join(self.log_parts())
        session = ObservedClientSession(owner, bound, controller, slot='save_009',
            read_log=lambda: self.log, guard=lambda: True, deadline=deadline)
        self.addCleanup(session.close)
        self.assertTrue(session.start())
        self.log += b'[X4LAN] AUTH_PARTICIPANT ERR'
        self.assertFalse(session.poll(.1))
        self.assertEqual(self.commands, [])
        self.log += b'OR state\n'
        with self.assertRaisesRegex(ValueError, 'client script reported'):
            session.poll(.1)
        self.assertEqual(self.commands, [])
        self.assertEqual(client.fileno(), -1)

    def test_replaced_log_is_rejected_before_queued_command(self):
        owner, client, bound, deadline = self.connect()
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        self.start_fake_participant(controller)
        self.log = b''.join(self.log_parts())
        session = ObservedClientSession(owner, bound, controller, slot='save_009',
            read_log=lambda: self.log, guard=lambda: True, deadline=deadline)
        self.addCleanup(session.close)
        self.assertTrue(session.start())
        self.log = b'other complete snapshot\n'
        with self.assertRaisesRegex(ValueError, 'changed or shrank'):
            session.poll(.1)
        self.assertEqual(self.commands, [])
        self.assertEqual(client.fileno(), -1)

    def test_partial_log_during_command_prevents_receipt(self):
        owner, client, bound, deadline = self.connect()
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        self.start_fake_participant(controller)
        self.log = b''.join(self.log_parts())
        self.partial_during_command = True
        session = ObservedClientSession(owner, bound, controller, slot='save_009',
            read_log=lambda: self.log, guard=lambda: True, deadline=deadline)
        self.addCleanup(session.close)
        self.assertTrue(session.start())
        with self.assertRaisesRegex(RuntimeError, 'incomplete during command'):
            while True:
                session.poll(.1)
        self.assertEqual(self.commands, ['resume'])
        self.assertTrue(self.server_done.wait(2))
        self.assertEqual(self.replies, [])
        self.assertEqual(client.fileno(), -1)

    def test_rejects_mismatched_offer_and_shorter_session_deadline(self):
        from dataclasses import replace
        for mode in ('offer', 'deadline'):
            with self.subTest(mode=mode):
                owner, client, bound, deadline = self.connect()
                controller = LocalParticipantControl(enabled=True, timeout=2)
                self.addCleanup(controller.close)
                wrong = MarkerBoundOffer(replace(bound.offer, attempt_id='e' * 32), bound.marker)
                with self.assertRaisesRegex(ValueError, 'matching staged offer'):
                    ObservedClientSession(owner, wrong if mode == 'offer' else bound, controller,
                        slot='save_009', read_log=lambda: b'', guard=lambda: True,
                        deadline=deadline if mode == 'offer' else deadline - 1)
                self.assertEqual(client.fileno(), -1)
                self.assertEqual(controller.sock.fileno(), -1)
                # Each iteration needs a fresh download and slot path.
                for path in (self.root/'download', self.root/'save'):
                    shutil.rmtree(path)

    def test_reentrant_guard_faults_without_claim(self):
        owner, client, bound, deadline = self.connect()
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        self.log = b''.join(self.log_parts())
        session = None
        def guard():
            try:
                session.poll()
            except RuntimeError:
                pass
            return True
        session = ObservedClientSession(owner, bound, controller, slot='save_009',
            read_log=lambda: self.log, guard=guard, deadline=deadline)
        with self.assertRaises((TimeoutError, RuntimeError)):
            session.start()
        self.assertTrue(self.server_done.wait(2))
        self.assertEqual(self.claims, [])
        self.assertEqual(client.fileno(), -1)
        self.assertEqual(controller.sock.fileno(), -1)

    def test_changed_internal_offer_fails_before_claim(self):
        from dataclasses import replace
        owner, client, bound, deadline = self.connect()
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        self.log = b''.join(self.log_parts())
        def guard():
            owner._load._bound = MarkerBoundOffer(replace(bound.offer, attempt_id='e' * 32), bound.marker)
            return True
        session = ObservedClientSession(owner, bound, controller, slot='save_009',
            read_log=lambda: self.log, guard=guard, deadline=deadline)
        with self.assertRaisesRegex(RuntimeError, 'staged load owner changed'):
            session.start()
        self.assertTrue(self.server_done.wait(2))
        self.assertEqual(self.claims, [])
        self.assertEqual(client.fileno(), -1)

    def test_other_thread_rejected_without_taking_owner(self):
        owner, client, bound, deadline = self.connect()
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        failures = []
        def construct():
            try:
                ObservedClientSession(owner, bound, controller, slot='save_009',
                    read_log=lambda: b'', guard=lambda: True, deadline=deadline)
            except BaseException as error:
                failures.append(error)
        thread = threading.Thread(target=construct)
        thread.start(); thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], RuntimeError)
        self.assertGreaterEqual(client.fileno(), 0)
        self.assertGreaterEqual(controller.sock.fileno(), 0)

    def test_controller_timeout_must_fit_participant_budget(self):
        owner, client, bound, deadline = self.connect()
        controller = LocalParticipantControl(enabled=True, timeout=300)
        self.addCleanup(controller.close)
        with self.assertRaisesRegex(ValueError, 'fresh local participant'):
            ObservedClientSession(owner, bound, controller, slot='save_009',
                read_log=lambda: b'', guard=lambda: True, deadline=deadline)
        self.assertEqual(client.fileno(), -1)
        self.assertEqual(controller.sock.fileno(), -1)

    def test_missing_keepalive_rejected_before_claim(self):
        owner, client, bound, deadline = self.connect(keepalive_interval=None)
        controller = LocalParticipantControl(enabled=True, timeout=2)
        self.addCleanup(controller.close)
        with self.assertRaisesRegex(ValueError, 'keepalive'):
            ObservedClientSession(owner, bound, controller, slot='save_009',
                read_log=lambda: b'', guard=lambda: True, deadline=deadline)
        self.assertEqual(self.claims, [])
        self.assertEqual(client.fileno(), -1)
        self.assertEqual(controller.sock.fileno(), -1)


if __name__ == '__main__':
    unittest.main()
