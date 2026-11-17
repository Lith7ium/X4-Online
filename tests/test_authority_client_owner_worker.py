"""Real subprocess and TCP/UDP/file protocols; X4 events are simulated."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from authority.experimental_tcp_control import offer_request
from authority.load_messages import Offer
from authority.trusted_load_messages import decode_bound_offer, decode_load_claim, encode_bound_offer
from authority.trusted_marker_load_session import MarkerBoundOffer
from lockstep.launcher.joinfiles import FileService
from test_authority_tcp_native_worker import identity, line

EPOCH = 'a' * 32
LEASE = 'b' * 32
ATTEMPT = 'c' * 32
MARKER = 'd' * 32


@unittest.skipUnless(sys.platform == 'linux', 'Linux diagnostic subprocess')
class ClientOwnerWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'save').mkdir()
        data = b'private synthetic save bytes'
        source = self.root / 'source'
        source.write_bytes(data)
        self.service = FileService('e' * 32, slots=(1,)).start()
        self.addCleanup(self.service.close)
        self.service.offer('j1.xml.gz', source)
        self.offer = Offer(world_epoch=EPOCH, connection_handle=1, baseline_id=1, load_generation=1,
            attempt_id=ATTEMPT, checkpoint_id='checkpoint-' + 'f' * 32,
            sha256=hashlib.sha256(data).hexdigest(), size=len(data), name='j1.xml.gz')
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        client = socket.create_connection(listener.getsockname(), timeout=3)
        self.server, _ = listener.accept()
        listener.close()
        self.server.settimeout(5)
        self.addCleanup(self.server.close)
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(('127.0.0.1', 0))
        self.engine = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.engine.bind(('127.0.0.1', 0))
        self.engine.settimeout(5)
        self.addCleanup(self.engine.close)
        self.ipc, child = socket.socketpair()
        self.ipc.settimeout(5)
        self.addCleanup(self.ipc.close)
        fds = (client.fileno(), self.udp.fileno(), child.fileno())
        self.process = subprocess.Popen([sys.executable, str(ROOT / 'tools/dev/authority_client_owner_worker.py'),
            *(str(fd) for fd in fds)], pass_fds=fds, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client.close()
        child.close()
        self.addCleanup(self.cleanup_process)
        self.ipc.sendall(json.dumps({'file_port': self.service.port, 'file_token': 'e' * 32,
            'deadline': time.monotonic() + 15, 'download': str(self.root / 'download'),
            'target': str(self.root / 'save/save_009.xml.gz')}).encode() + b'\n')
        self.assertEqual(line(self.server) + b'\n', offer_request())
        self.server.sendall(encode_bound_offer(MarkerBoundOffer(self.offer, MARKER)) + b'\n')
        staged = json.loads(line(self.ipc))
        self.assertEqual(staged['event'], 'staged')
        self.assertEqual(decode_bound_offer(staged['offer'].encode()).offer, self.offer)
        self.assertEqual((self.root / 'save/save_009.xml.gz').read_bytes(), data)
        self.assertEqual((self.root / 'save/save_009.xml.gz').stat().st_mode & 0o777, 0o400)

    def cleanup_process(self):
        self.udp.close()
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)

    def activate(self, **changes):
        config = {'command': 'activate', 'attempt': ATTEMPT, 'marker': MARKER,
                  'load_requested': True, 'paused': True, 'epoch': EPOCH, 'handle': 1,
                  'lease': LEASE, 'udp_peer': list(self.engine.getsockname()), 'udp_next_id': 2,
                  'controller_timeout': 3, 'client_process': identity()}
        config.update(changes)
        # Relinquish the supervisor's UDP copy before authorizing the child.
        self.udp.close()
        self.ipc.sendall(json.dumps(config).encode() + b'\n')

    def accept_claim(self):
        claim = decode_load_claim(line(self.server))
        self.assertEqual(claim.marker, MARKER)
        self.assertTrue(claim.load_event_observed and claim.paused_observed)
        self.server.sendall(json.dumps({'version': 1, 'kind': 'accepted', 'attempt_id': ATTEMPT}).encode() + b'\n')
        self.assertEqual(json.loads(line(self.ipc)), {'event': 'active'})

    def send_resume(self):
        self.server.sendall(json.dumps({'version': 1, 'kind': 'participant_command', 'epoch': EPOCH,
            'connection_handle': 1, 'request_id': 1, 'operation': 'resume'}).encode() + b'\n')
        data, peer = self.engine.recvfrom(1024)
        self.assertEqual(data, f'CMD|{LEASE}|{EPOCH}|2|resume'.encode())
        return peer

    def test_offer_claim_real_controller_receipt_and_stop(self):
        self.activate()
        self.accept_claim()
        peer = self.send_resume()
        self.engine.sendto(f'RECEIPT|{LEASE}|{EPOCH}|2|resume|confirmed'.encode(), peer)
        reply = json.loads(line(self.server))
        self.assertEqual((reply['kind'], reply['operation'], reply['status']),
                         ('participant_receipt', 'resume', 'confirmed'))
        self.ipc.sendall(b'{"command":"stop"}\n')
        self.assertEqual(json.loads(line(self.ipc)), {'event': 'stopped'})
        self.assertEqual(self.process.wait(timeout=5), 0)
        self.assertEqual(self.server.recv(1), b'')

    def test_invalid_observation_refuses_claim(self):
        self.activate(marker='0' * 32)
        self.assertEqual(json.loads(line(self.ipc)), {'event': 'failed'})
        self.assertEqual(self.process.wait(timeout=5), 1)
        self.assertEqual(self.server.recv(1), b'')

    def test_stop_before_receipt_is_not_success(self):
        self.activate()
        self.accept_claim()
        self.ipc.sendall(b'{"command":"stop"}\n')
        self.assertEqual(json.loads(line(self.ipc)), {'event': 'failed'})
        self.assertEqual(self.process.wait(timeout=5), 1)

    def test_supervisor_controls_udp_before_explicit_handoff(self):
        self.udp.settimeout(2)
        self.engine.sendto(b'supervisor-enrollment', self.udp.getsockname())
        data, _ = self.udp.recvfrom(1024)
        self.assertEqual(data, b'supervisor-enrollment')
        self.activate(marker='0' * 32)
        self.assertEqual(json.loads(line(self.ipc)), {'event': 'failed'})
        self.assertEqual(self.process.wait(timeout=5), 1)
        self.assertEqual(self.server.recv(1), b'')

    def test_owned_child_can_be_reaped_during_unanswered_claim(self):
        self.activate()
        claim = decode_load_claim(line(self.server))
        self.assertEqual(claim.marker, MARKER)
        # Admission is indeterminate after this claim: the real server may
        # already have accepted it even when no ACK has reached the child.
        self.process.kill()
        self.process.wait(timeout=5)
        self.assertEqual(self.server.recv(1), b'')

    def test_parent_disconnect_before_observation_does_not_claim(self):
        self.udp.close()
        self.ipc.close()
        self.assertEqual(self.process.wait(timeout=5), 1)
        self.assertEqual(self.server.recv(1), b'')

    def test_stop_during_udp_operation_sends_no_participant_receipt(self):
        self.activate()
        self.accept_claim()
        peer = self.send_resume()
        self.ipc.sendall(b'{"command":"stop"}\n')
        self.engine.sendto(f'RECEIPT|{LEASE}|{EPOCH}|2|resume|confirmed'.encode(), peer)
        self.assertEqual(json.loads(line(self.ipc)), {'event': 'failed'})
        self.assertEqual(self.process.wait(timeout=5), 1)
        self.assertEqual(self.server.recv(1), b'')
