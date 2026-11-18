"""Loopback fixture-session composition; Windows process and X4 are simulated.

Real TLS, file transfer, workspace, overlay, log parsing, TCP and UDP are used.
This is not a Windows, X4, Internet or gameplay test.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import socket
import ssl
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]

from authority import experimental_windows_fixture_overlay as overlay
from authority import windows_fixture_session as fixture_session
from authority.experimental_tcp_control import offer_request
from authority.experimental_tls_tunnel import start_server
from authority.load_messages import Offer
from authority.trusted_load_messages import decode_load_claim, encode_bound_offer
from authority.trusted_marker_load_session import MarkerBoundOffer
from lockstep.launcher.joinfiles import FileService
from test_authority_tls_tunnel_integration import TEST_CERTIFICATE, TEST_PRIVATE_KEY, listening_socket
import test_authority_windows_fixture_workspace as workspace_fixture


class AssembledFixtureSessionTest(unittest.TestCase):
    # The existing fixture doubles Windows APIs and view creation, but uses the
    # real workspace and temporary on-disk profile, save and overlay.
    setUp = workspace_fixture.WindowsFixtureWorkspaceTests.setUp
    _command = workspace_fixture.WindowsFixtureWorkspaceTests._command
    _create_view = workspace_fixture.WindowsFixtureWorkspaceTests._create_view

    def test_download_admit_command_and_cleanup_over_real_local_transports(self):
        content = b'isolated synthetic checkpoint'
        source = self.root / 'source.save'
        source.write_bytes(content)
        offer = Offer(world_epoch='a' * 32, connection_handle=1, baseline_id=1, load_generation=1,
                      attempt_id='c' * 32, checkpoint_id='checkpoint-' + 'd' * 32,
                      sha256=hashlib.sha256(content).hexdigest(), size=len(content), name='j1.xml.gz')
        bound = MarkerBoundOffer(offer, 'b' * 32)
        service = FileService('f' * 32, slots=(1,)).start()
        self.addCleanup(service.close)
        service.offer(offer.name, source)
        dll = self.root / 'fixture.dll'
        dll.write_bytes(b'MZ fixture DLL')
        dll_digest = hashlib.sha256(dll.read_bytes()).hexdigest()

        # Existing public test-only certificate; the production tunnel still
        # performs its real certificate fingerprint and shared-key checks.
        cert = self.root / 'certificate.pem'
        key = self.root / 'key.pem'
        cert.write_text(TEST_CERTIFICATE)
        key.write_text(TEST_PRIVATE_KEY)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert), str(key))
        fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(TEST_CERTIFICATE)).hexdigest()
        control_listener = listening_socket()
        self.addCleanup(control_listener.close)
        tls_listener = listening_socket()
        port = tls_listener.getsockname()[1]
        stop = threading.Event()
        receipt_ready = threading.Event()
        errors, claims, receipts, commands = [], [], [], []

        def control_server():
            try:
                connection, _ = control_listener.accept()
                connection.settimeout(10)
                with connection, connection.makefile('rb', buffering=0) as stream:
                    if stream.readline() != offer_request():
                        raise AssertionError('unexpected offer request')
                    connection.sendall(encode_bound_offer(bound) + b'\n')
                    while True:
                        line = stream.readline()
                        if not line:
                            raise AssertionError('missing claim')
                        frame = json.loads(line)
                        if frame.get('kind') != 'keepalive':
                            break
                        connection.sendall(json.dumps({'version': 1, 'kind': 'alive',
                            'attempt_id': frame['attempt_id'], 'sequence': frame['sequence']}).encode() + b'\n')
                    claims.append(decode_load_claim(line.rstrip(b'\n')))
                    connection.sendall(json.dumps({'version': 1, 'kind': 'accepted',
                                                   'attempt_id': offer.attempt_id}).encode() + b'\n')
                    command = {'version': 1, 'kind': 'participant_command', 'epoch': offer.world_epoch,
                               'connection_handle': 1, 'request_id': 1, 'operation': 'resume'}
                    connection.sendall(json.dumps(command).encode() + b'\n')
                    receipts.append(json.loads(stream.readline()))
                    receipt_ready.set()
                    stop.wait(10)
            except BaseException as error:
                errors.append(error)
                receipt_ready.set()

        server_thread = threading.Thread(target=control_server, name='fixture-control-server')
        server_thread.start()
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, name='fixture-tls-server')
        loop_thread.start()
        tunnel = asyncio.run_coroutine_threadsafe(start_server(listener=tls_listener, ssl_context=context,
            shared_key=b'k' * 32, control_port=control_listener.getsockname()[1],
            file_port=service.port), loop).result(timeout=5)

        workspace = self.workspace
        test = self
        processes = []

        class FakeX4Process:
            def __init__(self, *, enabled):
                if enabled is not True:
                    raise AssertionError('process not enabled')
                self.done = threading.Event()
                self.cleanup_confirmed = False
                self.thread = None
                processes.append(self)

            def start(self, view, *, profile_id, guard):
                test.assertEqual(profile_id, 45841)
                test.assertTrue(guard())
                installed = view / 'extensions' / 'x4_lan_lab'
                config = (installed / 'ui' / 'config.lua').read_text('ascii')
                for name in overlay._FIELDS:
                    value = 'save_009' if name == 'slot' else getattr(offer, name)
                    literal = str(value) if type(value) is int else json.dumps(value)
                    test.assertIn(name + '=' + literal, config)
                test.assertIn('authority_load_save_path=' + json.dumps(r'C:\Private\45841\save'), config)
                port_match = re.search(r'authority_participant_port=(\d+)', config)
                lease_match = re.search(r'authority_participant_lease="([0-9a-f]{32})"', config)
                test.assertIsNotNone(port_match)
                test.assertIsNotNone(lease_match)
                test.assertEqual((installed / 'native' / 'x4lan_net_64.dll').read_bytes(), dll.read_bytes())
                test.assertEqual((workspace.save_dir / 'save_009.xml.gz').read_bytes(), content)
                destination = ('127.0.0.1', int(port_match.group(1)))
                lease = lease_match.group(1)
                fields = '|'.join(str(value) for value in (offer.world_epoch, 1, 1, 1,
                                  offer.checkpoint_id, offer.sha256, offer.attempt_id, 'save_009'))
                workspace.log_path.write_text('[X4LAN] AUTH_DOWNLOAD_LOAD load_requested|' + fields + '\n' +
                    '[X4LAN] AUTH_MARKER load INSPECTED ' + bound.marker + '\n' +
                    '[X4LAN] AUTH_DOWNLOAD_LOAD pause_observed|' + fields + '\n')

                def participant():
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                            udp.bind(('127.0.0.1', 0))
                            udp.settimeout(.05)
                            while not self.done.is_set():
                                udp.sendto(('HELLO|' + lease + '|' + offer.world_epoch).encode(), destination)
                                try:
                                    data, peer = udp.recvfrom(1024)
                                except socket.timeout:
                                    continue
                                parts = data.decode('ascii').split('|')
                                if len(parts) != 5 or parts[:3] != ['CMD', lease, offer.world_epoch]:
                                    raise AssertionError('unexpected UDP command')
                                commands.append(parts[4])
                                udp.sendto('|'.join(('RECEIPT', *parts[1:], 'confirmed')).encode(), peer)
                    except BaseException as error:
                        errors.append(error)
                self.thread = threading.Thread(target=participant, name='fake-x4-participant')
                self.thread.start()

            def is_running(self):
                return self.thread is not None and self.thread.is_alive()

            def close(self):
                self.done.set()
                if self.thread is not None:
                    self.thread.join(3)
                    if self.thread.is_alive():
                        raise RuntimeError('fake X4 thread did not stop')
                    if not self.cleanup_confirmed:
                        test.assertTrue((workspace.view / 'extensions' / 'x4_lan_lab' /
                                         'ui' / 'config.lua').is_file())
                self.cleanup_confirmed = True
                return True

        try:
            # Only Windows path rendering and the OS/X4 process boundary are
            # substituted; installation and every transport remain real.
            with patch.object(overlay, '_windows_save_path', return_value=r'C:\Private\45841\save'), \
                 patch.object(fixture_session, 'WindowsX4Process', FakeX4Process):
                result = fixture_session.run_fixture_session(enabled=True, workspace=workspace,
                    server_host='127.0.0.1', server_port=port, server_fingerprint=fingerprint,
                    shared_key=b'k' * 32, file_token='f' * 32, file_slot=1, windows_dll=dll,
                    dll_sha256=dll_digest, deadline=time.monotonic() + 15, keepalive_interval=.2,
                    stop_requested=receipt_ready.is_set, io_timeout=3, participant_timeout=3)
            self.assertEqual(result, {'client_admitted': True, 'participant_receipts': 1,
                                      'owned_cleanup_confirmed': True, 'configuration_redacted': True})
            self.assertEqual(len(claims), 1)
            self.assertEqual(claims[0].marker, bound.marker)
            self.assertEqual(claims[0].receipt.attempt_id, offer.attempt_id)
            self.assertTrue(claims[0].load_event_observed)
            self.assertTrue(claims[0].paused_observed)
            self.assertEqual(len(receipts), 1)
            self.assertEqual(receipts[0]['status'], 'confirmed')
            self.assertEqual(receipts[0]['operation'], 'resume')
            self.assertEqual(receipts[0]['request_id'], 1)
            self.assertEqual(commands, ['resume'])
            self.assertEqual(errors, [])
            self.assertTrue(processes[0].cleanup_confirmed)
            self.assertFalse((workspace.view / 'extensions' / 'x4_lan_lab' / 'ui' / 'config.lua').exists())
            self.assertEqual((workspace.save_dir / 'save_009.xml.gz').read_bytes(), content)
        finally:
            stop.set()
            for process in processes:
                process.close()
            asyncio.run_coroutine_threadsafe(tunnel.close(), loop).result(timeout=5)
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(5)
            server_thread.join(5)
            self.assertFalse(loop_thread.is_alive())
            self.assertFalse(server_thread.is_alive())
            loop.close()


if __name__ == '__main__':
    unittest.main()
