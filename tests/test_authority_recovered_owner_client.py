"""Real local owner child and transports with synthetic X4 observations."""
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev'), str(ROOT / 'tests')]
import authority_tcp_native_live as native
import authority_recovered_owner_client as owner_client
import authority_recovered_server_client as server_client
import authority_recovered_loopback_server as recovered_server
from authority_recovered_owner_client import (RecoveredOwnerClient, _read_guarded_event,
    _require_fresh_join)
from authority_diagnostic_tls_link import DiagnosticTLSLink
from authority.checkpoints import CheckpointStore
from authority.experimental_local_host import ExperimentalLocalHost
from authority.experimental_tcp_control import ExperimentalTCPControl
from authority.save_transfer import SaveOffers
from authority.trusted_marker_load_session import TrustedMarkerLoadSession
from authority.world import WorldCoordinator
from lockstep.launcher.joinfiles import FileService
from test_authority_tcp_native_live import FreshEngine
from test_authority_tls_tunnel_integration import TEST_CERTIFICATE, TEST_PRIVATE_KEY


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'pidfd_open'), 'Linux pidfd required')
class RecoveredOwnerClientTests(unittest.TestCase):
    def test_fragmented_child_event_continues_guard_and_control_pump(self):
        participant = RecoveredOwnerClient(time.monotonic() + 5, Path('/synthetic'))
        participant.remote_ipc, writer = socket.socketpair()
        participant.remote_ipc.setblocking(False)
        participant.remote_helper = SimpleNamespace(proc=SimpleNamespace(poll=lambda: None))
        guard_calls = []
        poll_calls = []
        participant.control = SimpleNamespace(poll=lambda timeout: poll_calls.append(timeout))
        first_fragment = threading.Event()
        release_fragment = threading.Event()
        failures = []

        def send_fragmented_event():
            try:
                writer.sendall(b'{"ev')
                first_fragment.set()
                if not release_fragment.wait(3):
                    raise TimeoutError('supervisor did not pump a fragmented event')
                writer.sendall(b'ent":"active"}\n')
            except BaseException as error:
                failures.append(error)

        def guard():
            guard_calls.append(True)
            if first_fragment.is_set() and len(guard_calls) >= 2:
                release_fragment.set()
            return True

        thread = threading.Thread(target=send_fragmented_event)
        thread.start()
        try:
            participant._wait_event('active', time.monotonic() + 4, guard, pump_control=True)
            self.assertGreaterEqual(len(guard_calls), 2)
            self.assertGreaterEqual(len(poll_calls), 2)
        finally:
            release_fragment.set()
            thread.join(3)
            writer.close()
            participant.remote_ipc.close()
            participant.sock.close()
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])

    def test_fresh_join_rejects_missing_source_reused_id_or_marker(self):
        ticket = {'checkpoint_id': 'new-id'}
        marker = 'new-marker'
        _require_fresh_join(SimpleNamespace(checkpoint_id='old-id', marker='old-marker'), ticket, marker)
        cases = (None, SimpleNamespace(checkpoint_id='new-id', marker='old-marker'),
                 SimpleNamespace(checkpoint_id='old-id', marker='new-marker'))
        for checkpoint in cases:
            with self.subTest(checkpoint=checkpoint), self.assertRaisesRegex(ValueError, 'not fresh'):
                _require_fresh_join(checkpoint, ticket, marker)

    def test_guarded_reader_rejects_invalid_or_late_frames(self):
        cases = ((b'abc\nextra', 16, ValueError), (b'12345\n', 4, ValueError),
                 (b'', 16, ConnectionError))
        for data, limit, error in cases:
            with self.subTest(data=data):
                reader, writer = socket.socketpair()
                with reader, writer:
                    # One write puts the extra bytes in the same available frame.
                    if data:
                        writer.sendall(data)
                    else:
                        writer.close()
                    with self.assertRaises(error):
                        _read_guarded_event(reader, limit, time.monotonic() + 2, lambda: None)

    def test_guarded_reader_rejects_timeout_and_guard_failure(self):
        reader, writer = socket.socketpair()
        with reader, writer:
            with self.assertRaises(TimeoutError):
                _read_guarded_event(reader, 16, time.monotonic() - 1, lambda: None)
            def fail_guard():
                raise RuntimeError('guard failed')
            with self.assertRaisesRegex(RuntimeError, 'guard failed'):
                _read_guarded_event(reader, 16, time.monotonic() + 1, fail_guard)

    def test_guarded_reader_rejects_frame_when_guard_runs_past_deadline(self):
        reader, writer = socket.socketpair()
        with reader, writer:
            writer.sendall(b'ok\n')
            clock = iter((1.0, 1.0, 2.0, 2.0, 2.0, 2.0))
            with patch('authority_recovered_owner_client.time.monotonic', side_effect=clock):
                with self.assertRaises(TimeoutError):
                    _read_guarded_event(reader, 16, 1.5, lambda: None)

    def test_load_claim_resume_and_stop_with_real_child_and_synthetic_x4(self):
        self.exercise(fail_during_claim=False)

    def test_guard_failure_during_claim_fences_child_before_resume(self):
        self.exercise(fail_during_claim=True)

    def test_guard_failure_after_resume_dispatch_fences_admission(self):
        self.exercise(fail_during_claim=False, fail_during_resume=True)

    def exercise(self, *, fail_during_claim, fail_during_resume=False):
        # The coordinator, file service, TCP/UDP and child process are real.
        # Process/log observations and game-side UDP receipts are simulated.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'store').mkdir()
            (root / 'game').mkdir()
            (root / 'game/X4').symlink_to('/proc/self/exe')
            output = root / 'diagnostic'
            (output / 'client/save').mkdir(parents=True)
            store = CheckpointStore(root / 'store')
            service = FileService('f' * 32, slots=(1,)).start()
            engine = FreshEngine(root)
            engine._timeout = 5
            world = WorldCoordinator('a' * 32, engine, store, SaveOffers(service, store))
            session = TrustedMarkerLoadSession(world, enabled=True)
            control = ExperimentalTCPControl(session, enabled=True, idle_timeout=30, keepalive_enabled=True)
            host = ExperimentalLocalHost(world, control, service, enabled=True)
            owner_guard_slot = [None]
            def verify_process():
                if owner_guard_slot[0] is not None:
                    return owner_guard_slot[0]()
                return True
            world._participants = recovered_server.RecoveredGuardedParticipants(
                host, guard_process=verify_process, enabled=True, timeout=5)
            deadline = time.monotonic() + 30
            participant = RecoveredOwnerClient(deadline, root / 'source')
            participant.checkpoint = SimpleNamespace(checkpoint_id='initial', marker='0' * 32)
            participant.session, participant.control, participant.host = session, control, host
            participant.participants = world._participants
            participant._owner_guard_slot = owner_guard_slot
            process_identity = (os.getpid(), native.marked.base.live.start_ticks(os.getpid()))
            udp = None
            thread = None
            stop = threading.Event()
            game_operations = []
            guard_calls = []
            accept_guard_counts = []
            claim_started = [False]
            resume_dispatched = threading.Event()
            resume_guard_failed = threading.Event()
            original_accept = session.accept
            try:
                certificate, private_key = root / 'test-cert.pem', root / 'test-key.pem'
                certificate.write_text(TEST_CERTIFICATE, encoding='ascii')
                private_key.write_text(TEST_PRIVATE_KEY, encoding='ascii')
                link = DiagnosticTLSLink(participant)
                participant.diagnostic_tls_link = link
                participant.client_tcp, participant.server_tcp = link.start(
                    certificate, private_key, service.port, deadline)
                participant.diagnostic_file_port = link.file_port
                def guard():
                    guard_calls.append(time.monotonic())
                    link.check()
                    if fail_during_claim and claim_started[0]:
                        return False
                    if fail_during_resume and resume_dispatched.is_set():
                        resume_guard_failed.set()
                        return False
                    return True
                participant._diagnostic_server_guard = guard
                handle = host.adopt(participant.server_tcp)
                baseline = server_client.prepare_join_baseline(host, world, deadline, guard)
                ticket, target = participant.offer_and_download(world, service, handle, output / 'client', output / 'client')
                server_client.verify_join_offer(ticket, participant.marker, baseline)
                self.assertEqual(target.stat().st_mode & 0o777, 0o400)

                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp.bind(('127.0.0.1', 0))
                udp.settimeout(.05)
                destination = participant.sock.getsockname()
                def fake_game():
                    while not stop.is_set():
                        try:
                            udp.sendto(('HELLO|' + participant.lease + '|' + 'a' * 32).encode(), destination)
                            data, peer = udp.recvfrom(1024)
                        except socket.timeout:
                            continue
                        except OSError:
                            return
                        fields = data.decode('ascii').split('|')
                        if len(fields) == 5 and fields[0] == 'CMD':
                            _, lease, epoch, number, operation = fields
                            game_operations.append((number, operation))
                            if operation == 'resume' and fail_during_resume:
                                resume_dispatched.set()
                                if not resume_guard_failed.wait(5):
                                    return
                            udp.sendto('|'.join(('RECEIPT', lease, epoch, number, operation, 'confirmed')).encode(), peer)
                thread = threading.Thread(target=fake_game)
                thread.start()

                def tracked_accept(*args, **kwargs):
                    calls_before = len(guard_calls)
                    claim_started[0] = True
                    try:
                        return original_accept(*args, **kwargs)
                    finally:
                        accept_guard_counts.append(len(guard_calls) - calls_before)
                session.accept = tracked_accept

                result = {}
                with patch.object(participant, 'verify_logs'), \
                     patch.object(participant, 'check_server_files', return_value=True), \
                     patch.object(native.marked.base.client, 'game_identity', return_value=process_identity), \
                     patch.object(owner_client, 'send_frame', wraps=owner_client.send_frame) as send_frame:
                    def join():
                        participant.on_ready(world=world, handle=handle, ticket=ticket, target=target,
                            server_identity=process_identity, server_proc=object(), server_started=process_identity[1],
                            client_identity=process_identity, client_proc=object(), client_started=process_identity[1],
                            game=root / 'game', out=output, deadline=deadline, result=result, check_protected=guard)
                    if fail_during_claim or fail_during_resume:
                        with self.assertRaises(RuntimeError):
                            join()
                    else:
                        join()
                self.assertEqual(len(accept_guard_counts), 1)
                self.assertGreater(accept_guard_counts[0], 0)
                self.assertIsNone(owner_guard_slot[0])
                if fail_during_resume:
                    self.assertTrue(resume_dispatched.is_set())
                    self.assertTrue(resume_guard_failed.is_set())
                    self.assertEqual(game_operations, [('1', 'pause'), ('2', 'resume')])
                    self.assertEqual(result['server_state'], 'indeterminate')
                    self.assertNotIn('native_server_and_client_resume_confirmed', result)
                    self.assertNotIn('helper_clean_exit', result)
                    self.assertNotIn(b'{"command":"stop"}',
                                     [call.args[1] for call in send_frame.call_args_list])
                    participant.cleanup_diagnostic()
                    self.assertTrue(all(helper.proc.poll() is not None for helper in participant.helpers))
                    return
                if fail_during_claim:
                    self.assertEqual(game_operations, [('1', 'pause')])
                    self.assertIsNone(result['client_admitted'])
                    self.assertEqual(result['admission_state'], 'indeterminate')
                    participant.cleanup_diagnostic()
                    self.assertTrue(all(helper.proc.poll() is not None for helper in participant.helpers))
                    return
                self.assertTrue(result['client_admitted'])
                self.assertTrue(result['native_server_and_client_resume_confirmed'])
                self.assertTrue(result['helper_clean_exit'])
                self.assertEqual(game_operations, [('1', 'pause'), ('2', 'resume')])
                self.assertGreater(len(guard_calls), 2)
                participant.cleanup_diagnostic()
                final = server_client.settle_departure(host, world, control, participant.server_tcp,
                    deadline, lambda: True, ticket, participant.marker)
                self.assertEqual(world.session.state, 'paused')
                self.assertEqual(world.session.players, ())
                self.assertNotEqual(final.checkpoint_id, baseline.checkpoint_id)
            finally:
                session.accept = original_accept
                stop.set()
                resume_guard_failed.set()
                if udp is not None:
                    udp.close()
                if thread is not None:
                    thread.join(3)
                    self.assertFalse(thread.is_alive())
                participant.cleanup_diagnostic()
                if not (control._closed or control._failed):
                    control.close()
                service.close_and_drain(timeout=3)


if __name__ == '__main__':
    unittest.main()
