"""Local process tests for the private TLS diagnostic link; no X4 is started."""
import array
import hashlib
import json
import os
import pathlib
import select
import threading
import socket
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools/dev'), str(ROOT / 'src'), str(ROOT / 'tests')]
from authority_diagnostic_tls_link import DiagnosticTLSLink, _connected_pair, _verify_pairs
from test_authority_tls_tunnel_integration import TEST_CERTIFICATE, TEST_PRIVATE_KEY


class Participant:
    def __init__(self):
        self.helpers = []


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'pidfd_open'), 'Linux pidfd required')
class DiagnosticTLSLinkTests(unittest.TestCase):
    def test_rejects_incorrect_socket_pairing(self):
        first = _connected_pair()
        second = _connected_pair()
        try:
            _verify_pairs([first, second])
            with self.assertRaises(RuntimeError):
                _verify_pairs([(first[0], second[1]), (second[0], first[1])])
        finally:
            for endpoint in first + second:
                endpoint.close()

    def test_control_file_and_owned_gateway_lifecycle(self):
        participant = Participant()
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            certificate, key = path / 'cert.pem', path / 'key.pem'
            certificate.write_text(TEST_CERTIFICATE)
            key.write_text(TEST_PRIVATE_KEY)
            service = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            service.bind(('127.0.0.1', 0))
            service.listen(1)
            service.settimeout(5)
            link = DiagnosticTLSLink(participant)
            client = server = file_client = backend = None
            try:
                client, server = link.start(certificate, key, service.getsockname()[1], time.monotonic() + 15)
                client.settimeout(5)
                server.settimeout(5)
                client.sendall(b'control')
                self.assertEqual(server.recv(7), b'control')
                server.sendall(b'ack')
                self.assertEqual(client.recv(3), b'ack')
                file_client = socket.create_connection(('127.0.0.1', link.file_port), timeout=5)
                backend, _ = service.accept()
                file_client.settimeout(5)
                backend.settimeout(5)
                file_client.sendall(b'file')
                self.assertEqual(backend.recv(4), b'file')
                backend.sendall(b'ok')
                self.assertEqual(file_client.recv(2), b'ok')
                self.assertTrue(link.check())
                link.expect_departure()
                client.close()
                client = None
                self.assertEqual(server.recv(1), b'')
                server.close()
                server = None
                link.check()
            finally:
                for endpoint in (client, server, file_client, backend, service):
                    if endpoint is not None:
                        endpoint.close()
                link._cleanup()
            self.assertTrue(all(helper.proc.poll() is not None for helper in link.helpers))
            with self.assertRaises(RuntimeError):
                link.check()


    def test_two_links_keep_independent_control_and_file_channels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            certificate, key = path / 'cert.pem', path / 'key.pem'
            certificate.write_text(TEST_CERTIFICATE)
            key.write_text(TEST_PRIVATE_KEY)
            service = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            service.bind(('127.0.0.1', 0))
            service.listen(2)
            service.settimeout(5)
            links = [DiagnosticTLSLink(Participant()) for _ in range(2)]
            endpoints = []

            def receive_exact(sock, length):
                data = bytearray()
                while len(data) < length:
                    chunk = sock.recv(length - len(data))
                    if not chunk:
                        raise EOFError('TLS stream closed before message completed')
                    data.extend(chunk)
                return bytes(data)

            try:
                for link in links:
                    client, server = link.start(certificate, key, service.getsockname()[1], time.monotonic() + 15)
                    client.settimeout(5)
                    server.settimeout(5)
                    endpoints.append((client, server))
                for index, (client, server) in enumerate(endpoints):
                    message = ('client-%d' % index).encode('ascii')
                    client.sendall(message)
                    self.assertEqual(receive_exact(server, len(message)), message)
                links[0].expect_departure()
                endpoints[0][0].close()
                self.assertEqual(endpoints[0][1].recv(1), b'')
                self.assertTrue(links[1].check())
                endpoints[1][1].sendall(b'still-active')
                self.assertEqual(receive_exact(endpoints[1][0], 12), b'still-active')
                file_client = socket.create_connection(('127.0.0.1', links[1].file_port), timeout=5)
                file_server, _ = service.accept()
                file_server.settimeout(5)
                endpoints.append((file_client, file_server))
                endpoints[-1][0].sendall(b'save')
                self.assertEqual(receive_exact(endpoints[-1][1], 4), b'save')
            finally:
                for pair in endpoints:
                    for endpoint in pair:
                        endpoint.close()
                for link in reversed(links):
                    link._cleanup()
                service.close()
            self.assertTrue(all(helper.proc.poll() is not None for link in links for helper in link.helpers))

    def test_real_load_owner_hands_off_to_real_worker_then_stops(self):
        from authority.load_messages import Offer, Receipt
        from authority.trusted_marker_load_session import MarkerBoundOffer
        from authority.trusted_load_messages import encode_bound_offer, encode_load_claim
        from authority.experimental_client_load import HonestClientLoadClaim
        from lockstep.launcher.joinfiles import FileService
        from authority_helper_lifecycle import OwnedHelper
        from test_authority_tcp_native_worker import identity, line

        participant = Participant()
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            certificate, key = path / 'cert.pem', path / 'key.pem'
            certificate.write_text(TEST_CERTIFICATE)
            key.write_text(TEST_PRIVATE_KEY)
            (path / 'save').mkdir()
            content = b'diagnostic save bytes'
            source = path / 'source'
            source.write_bytes(content)
            service = FileService('a' * 32, slots=(1,)).start()
            service.offer('j1.xml.gz', source)
            offer = Offer(world_epoch='a' * 32, connection_handle=1, baseline_id=1,
                load_generation=1, attempt_id='c' * 32, checkpoint_id='checkpoint-' + 'd' * 32,
                sha256=hashlib.sha256(content).hexdigest(), size=len(content), name='j1.xml.gz')
            link = DiagnosticTLSLink(participant)
            client = server = owner_parent = owner_child = worker_parent = worker_child = udp = engine = None
            helpers = []
            failures = []
            try:
                client, server = link.start(certificate, key, service.port, time.monotonic() + 20)
                server.settimeout(8)
                def host():
                    try:
                        with server.makefile('rb') as stream:
                            self.assertEqual(json.loads(stream.readline())['kind'], 'offer_request')
                            server.sendall(encode_bound_offer(MarkerBoundOffer(offer, 'b' * 32)) + b'\n')
                            claim = json.loads(stream.readline())
                            self.assertEqual(claim['kind'], 'marked_claim')
                            server.sendall(json.dumps({'version':1, 'kind':'accepted',
                                'attempt_id':offer.attempt_id}).encode() + b'\n')
                            self.assertEqual(stream.readline(), b'')
                    except BaseException as error:
                        failures.append(error)
                thread = threading.Thread(target=host)
                thread.start()
                owner_parent, owner_child = socket.socketpair()
                owner_parent.settimeout(8)
                owner = OwnedHelper([sys.executable, str(ROOT/'tools/dev/authority_remote_load_owner.py'),
                    str(client.fileno()), str(owner_child.fileno())], registry=helpers,
                    pass_fds=(client.fileno(), owner_child.fileno()))
                owner.release()
                client.close(); client = None
                owner_child.close(); owner_child = None
                owner_parent.sendall(json.dumps({'file_port':link.file_port, 'file_token':'a'*32,
                    'deadline':time.monotonic()+15, 'download':str(path/'download'),
                    'target':str(path/'save/save_009.xml.gz')}).encode()+b'\n')
                self.assertEqual(json.loads(line(owner_parent))['event'], 'staged')
                self.assertEqual((path/'save/save_009.xml.gz').read_bytes(), content)
                owner_parent.sendall(b'{"command":"claim"}\n')
                data, ancillary, flags, _ = owner_parent.recvmsg(1, socket.CMSG_SPACE(array.array('i').itemsize))
                self.assertEqual(data, b'F')
                self.assertEqual(flags & socket.MSG_CTRUNC, 0)
                rights = array.array('i')
                for level, kind, value in ancillary:
                    if (level, kind) == (socket.SOL_SOCKET, socket.SCM_RIGHTS):
                        rights.frombytes(value[:len(value) - len(value) % rights.itemsize])
                self.assertEqual(len(rights), 1)
                self.assertEqual(owner.proc.wait(timeout=5), 0)
                client = socket.socket(fileno=rights[0])
                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp.bind(('127.0.0.1', 0))
                engine = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                engine.bind(('127.0.0.1', 0))
                worker_parent, worker_child = socket.socketpair()
                worker_parent.settimeout(8)
                receipt = Receipt('a'*32, 1, 1, 1, 'c'*32, offer.checkpoint_id, offer.sha256, offer.size)
                config = {'version':1, 'claim':encode_load_claim(HonestClientLoadClaim(receipt, 'b'*32, True, True)).decode(),
                    'epoch':'a'*32, 'handle':1, 'lease':'e'*32, 'udp_peer':list(engine.getsockname()),
                    'udp_next_id':1, 'deadline':time.monotonic()+10, 'controller_timeout':5,
                    'client_process':identity(), 'already_admitted':True}
                fds = (client.fileno(), udp.fileno(), worker_child.fileno())
                worker = OwnedHelper([sys.executable, str(ROOT/'tools/dev/authority_tcp_native_worker.py'),
                    *(str(fd) for fd in fds)], registry=helpers, pass_fds=fds)
                worker.release()
                client.close(); client = None
                udp.close(); udp = None
                worker_child.close(); worker_child = None
                worker_parent.sendall(json.dumps(config).encode()+b'\n')
                self.assertEqual(json.loads(line(worker_parent)), {'event':'active'})
                link.check()
                link.expect_departure()
                worker_parent.sendall(b'{"command":"stop"}\n')
                self.assertEqual(json.loads(line(worker_parent)), {'event':'stopped'})
                self.assertEqual(worker.proc.wait(timeout=5), 0)
                thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertFalse(failures, repr(failures))
                link.check()
            finally:
                for helper in reversed(helpers):
                    helper.stop()
                for sock in (client, server, owner_parent, owner_child, worker_parent, worker_child, udp, engine):
                    if sock is not None:
                        sock.close()
                link._cleanup()
                service.close()

    def test_gateway_exit_fails_closed(self):
        participant = Participant()
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            certificate, key = path / 'cert.pem', path / 'key.pem'
            certificate.write_text(TEST_CERTIFICATE)
            key.write_text(TEST_PRIVATE_KEY)
            link = DiagnosticTLSLink(participant)
            client = server = None
            try:
                client, server = link.start(certificate, key, 9, time.monotonic() + 15)
                target_fd = link.helpers[0].pidfd
                saved_fd = os.dup(target_fd)
                try:
                    os.dup2(link.helpers[1].pidfd, target_fd)
                    with self.assertRaises(RuntimeError):
                        link.check()
                finally:
                    os.dup2(saved_fd, target_fd)
                    os.close(saved_fd)
                self.assertTrue(link.check())
                link.helpers[0].stop()
                with self.assertRaises(RuntimeError):
                    link.check()
            finally:
                if client is not None:
                    client.close()
                if server is not None:
                    server.close()
                link._cleanup()

    def test_unexpected_relay_end_fails_closed_before_departure(self):
        participant = Participant()
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            certificate, key = path / 'cert.pem', path / 'key.pem'
            certificate.write_text(TEST_CERTIFICATE)
            key.write_text(TEST_PRIVATE_KEY)
            link = DiagnosticTLSLink(participant)
            client = server = None
            try:
                client, server = link.start(certificate, key, 9, time.monotonic() + 15)
                client.close(); client = None
                server.close(); server = None
                ready, _, _ = select.select(link.ipc, [], [], 5)
                self.assertTrue(ready, 'relay completion was not reported')
                with self.assertRaises(RuntimeError):
                    link.check()
            finally:
                if client is not None:
                    client.close()
                if server is not None:
                    server.close()
                link._cleanup()
