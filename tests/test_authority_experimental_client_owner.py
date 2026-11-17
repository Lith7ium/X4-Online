"""One owner, real wire/file protocols and simulated X4 observations."""
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority.experimental_client_owner import ExperimentalClientOwner
from authority.experimental_remote_load_client import ExperimentalRemoteLoadClient
from authority.experimental_tcp_control import offer_request
from authority.load_messages import Offer
from authority.trusted_load_messages import decode_load_claim, encode_bound_offer
from authority.trusted_marker_load_session import MarkerBoundOffer
from lockstep.launcher.joinfiles import FileService


class Controller:
    def __init__(self):
        self.calls = []

    def pause(self, handles):
        self.calls.append(('pause', handles))
        return True

    def resume(self, handles):
        self.calls.append(('resume', handles))
        return True


class ClientOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.content = b'one isolated offered save'
        source = self.root / 'source'
        source.write_bytes(self.content)
        self.marker = 'b' * 32
        self.offer = Offer(world_epoch='epoch', connection_handle=1, baseline_id=1,
            load_generation=1, attempt_id='c' * 32, checkpoint_id='checkpoint-' + 'd' * 32,
            sha256=hashlib.sha256(self.content).hexdigest(), size=len(self.content), name='j1.xml.gz')
        self.service = FileService('a' * 32, slots=(1,)).start()
        self.addCleanup(self.service.close)
        self.service.offer('j1.xml.gz', source)

    def connect(self, *, accepted_attempt=None, send_command=True, host='127.0.0.1'):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind((host, 0))
        listener.listen(1)
        listener.settimeout(5)
        client = socket.create_connection(listener.getsockname(), timeout=5)
        errors, claims, replies = [], [], []

        def server():
            try:
                conn, _ = listener.accept()
                conn.settimeout(5)
                with conn, conn.makefile('rb', buffering=0) as stream:
                    if stream.readline() != offer_request():
                        raise AssertionError('unexpected offer request')
                    conn.sendall(encode_bound_offer(MarkerBoundOffer(self.offer, self.marker)) + b'\n')
                    line = stream.readline()
                    if not line:
                        return
                    claims.append(decode_load_claim(line.rstrip(b'\n')))
                    accepted = {'version': 1, 'kind': 'accepted',
                                'attempt_id': accepted_attempt or self.offer.attempt_id}
                    conn.sendall(json.dumps(accepted).encode() + b'\n')
                    if send_command:
                        command = {'version': 1, 'kind': 'participant_command', 'epoch': 'epoch',
                                   'connection_handle': 1, 'request_id': 1, 'operation': 'resume'}
                        conn.sendall(json.dumps(command).encode() + b'\n')
                        reply = stream.readline()
                        if reply:
                            replies.append(json.loads(reply))
            except BaseException as error:
                errors.append(error)
            finally:
                listener.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.addCleanup(lambda: thread.join(6))
        owner = ExperimentalClientOwner(client, enabled=True, file_host='127.0.0.1',
            file_port=self.service.port, file_token='a' * 32, file_slot=1,
            deadline=time.monotonic() + 10, io_timeout=3)
        self.addCleanup(owner.close)
        return owner, client, thread, errors, claims, replies

    def observe(self, owner):
        bound = owner.request_offer()
        path = owner.download(self.root / 'download')
        self.assertEqual(path.read_bytes(), self.content)
        owner.verify_staged(path)
        owner.load_requested(bound.offer.attempt_id)
        owner.loaded_marker(bound.offer.attempt_id, bound.marker)
        owner.paused(bound.offer.attempt_id, True)
        return bound

    def test_real_load_handoff_and_participant_receipt(self):
        owner, client, thread, errors, claims, replies = self.connect()
        bound = self.observe(owner)
        controller = Controller()
        owner.activate(bound.offer.attempt_id, controller, participant_timeout=3)
        deadline = time.monotonic() + 4
        while not owner.poll(.1):
            if time.monotonic() >= deadline:
                self.fail('participant receipt timed out')
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].marker, self.marker)
        self.assertEqual(controller.calls, [('resume', (1,))])
        self.assertEqual(replies[0]['status'], 'confirmed')
        owner.close()
        self.assertEqual(client.fileno(), -1)

    def test_reentrant_controller_fences_owner_before_reply(self):
        owner, client, thread, errors, _, replies = self.connect()
        bound = self.observe(owner)
        class ReentrantController(Controller):
            def resume(self, handles):
                try:
                    owner.poll()
                except RuntimeError:
                    pass
                return True
        owner.activate(bound.offer.attempt_id, ReentrantController(), participant_timeout=3)
        with self.assertRaises(RuntimeError):
            while True:
                owner.poll(.1)
        self.assertEqual(client.fileno(), -1)
        thread.join(4)
        self.assertEqual(errors, [])
        self.assertEqual(replies, [])

    def test_wrong_admission_closes_without_running_controller(self):
        owner, client, thread, errors, _, _ = self.connect(accepted_attempt='f' * 32, send_command=False)
        bound = self.observe(owner)
        controller = Controller()
        with self.assertRaises(ValueError):
            owner.activate(bound.offer.attempt_id, controller)
        self.assertEqual(client.fileno(), -1)
        self.assertEqual(controller.calls, [])
        thread.join(4)
        self.assertEqual(errors, [])

    def test_interruption_after_transfer_closes_original_socket(self):
        owner, client, thread, errors, _, _ = self.connect(send_command=False)
        bound = self.observe(owner)
        original_transfer = ExperimentalRemoteLoadClient.take_connection
        def interrupted_transfer(load):
            original_transfer(load)
            raise InterruptedError('interrupted immediately after transfer')
        with patch.object(ExperimentalRemoteLoadClient, 'take_connection', interrupted_transfer):
            with self.assertRaises(InterruptedError):
                owner.activate(bound.offer.attempt_id, Controller())
        self.assertEqual(client.fileno(), -1)
        thread.join(4)
        self.assertEqual(errors, [])

    def test_invalid_controller_closes_without_claim(self):
        owner, client, thread, errors, claims, _ = self.connect(send_command=False)
        bound = self.observe(owner)
        with self.assertRaises(ValueError):
            owner.activate(bound.offer.attempt_id, object())
        self.assertEqual(client.fileno(), -1)
        thread.join(4)
        self.assertEqual(errors, [])
        self.assertEqual(claims, [])

    def test_reentrant_controller_property_does_not_send_claim(self):
        owner, client, thread, errors, claims, _ = self.connect(send_command=False)
        bound = self.observe(owner)
        class ReentrantController:
            @property
            def pause(self):
                try:
                    owner.close()
                except RuntimeError:
                    pass
                return lambda handles: True
            def resume(self, handles):
                return True
        with self.assertRaises(RuntimeError):
            owner.activate(bound.offer.attempt_id, ReentrantController())
        self.assertEqual(client.fileno(), -1)
        thread.join(4)
        self.assertEqual(errors, [])
        self.assertEqual(claims, [])

    def test_invalid_participant_timeout_closes_without_claim(self):
        owner, client, thread, errors, claims, _ = self.connect(send_command=False)
        bound = self.observe(owner)
        with self.assertRaises(ValueError):
            owner.activate(bound.offer.attempt_id, Controller(), participant_timeout=0)
        self.assertEqual(client.fileno(), -1)
        thread.join(4)
        self.assertEqual(errors, [])
        self.assertEqual(claims, [])

    @unittest.skipUnless(sys.platform == 'linux', 'requires Linux loopback aliases')
    def test_nonmatching_loopback_peer_closes_without_claim(self):
        owner, client, thread, errors, claims, _ = self.connect(send_command=False, host='127.0.0.2')
        bound = self.observe(owner)
        with self.assertRaises(ValueError):
            owner.activate(bound.offer.attempt_id, Controller())
        self.assertEqual(client.fileno(), -1)
        thread.join(4)
        self.assertEqual(errors, [])
        self.assertEqual(claims, [])

    def test_foreign_thread_rejected_without_losing_connection(self):
        owner, client, thread, errors, _, _ = self.connect(send_command=False)
        caught = []
        def misuse():
            try:
                owner.close()
            except RuntimeError as error:
                caught.append(str(error))
        foreign = threading.Thread(target=misuse)
        foreign.start()
        foreign.join(3)
        self.assertEqual(len(caught), 1)
        self.assertNotEqual(client.fileno(), -1)
        self.assertEqual(owner.request_offer().offer, self.offer)
        owner.close()
        thread.join(4)
        self.assertEqual(errors, [])

    def test_rejected_constructor_preserves_caller_socket(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        client = socket.create_connection(listener.getsockname(), timeout=3)
        peer, _ = listener.accept()
        try:
            with self.assertRaises(ValueError):
                ExperimentalClientOwner(client, enabled=False, file_host='127.0.0.1',
                    file_port=self.service.port, file_token='a' * 32, file_slot=1,
                    deadline=time.monotonic() + 10)
            self.assertNotEqual(client.fileno(), -1)
        finally:
            client.close()
            peer.close()
            listener.close()
