"""Offline ownership and evidence checks; no X4 process is started."""
from pathlib import Path
import socket
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_recovered_server_client as subject
import authority_recovered_loopback_server as supervisor


class ServerClientTests(unittest.TestCase):
    def make_world(self):
        checkpoint = SimpleNamespace(checkpoint_id='checkpoint-second', sha256='b'*64, marker='c'*32)
        store = SimpleNamespace(latest_marked_confirmed=Mock(return_value=checkpoint),
                                latest=Mock(return_value=checkpoint))
        session = SimpleNamespace(state='paused', pending=None, save_required=False,
                                  baseline_id=9, players=())
        service = SimpleNamespace(lock=threading.RLock(), offered={})
        offers = SimpleNamespace(names=set(), service=service)
        world = SimpleNamespace(session=session, _baseline=(9, checkpoint), _store=store,
                                _load_offers={}, _offers=offers)
        return world, checkpoint

    def test_later_join_reuses_confirmed_paused_checkpoint(self):
        world, checkpoint = self.make_world()
        host = Mock()
        actual = subject.prepare_join_baseline(host, world, time.monotonic()+2, Mock(), checkpoint)
        self.assertEqual(actual, checkpoint)
        host.tick.assert_not_called()
        with self.assertRaises(ValueError):
            subject.prepare_join_baseline(host, world, time.monotonic()+2, Mock(), object())
        world._store.latest.return_value = object()
        with self.assertRaises(ValueError): subject.confirmed_baseline(world)

    def test_first_join_completes_pending_pause_and_save(self):
        world, checkpoint = self.make_world()
        world.session.pending = SimpleNamespace(operation='pause')
        operations = []
        def tick(_timeout):
            operations.append(world.session.pending.operation)
            world.session.pending = (SimpleNamespace(operation='save') if operations == ['pause'] else None)
        self.assertEqual(subject.prepare_join_baseline(SimpleNamespace(tick=tick), world,
                         time.monotonic()+2, Mock()), checkpoint)
        self.assertEqual(operations, ['pause', 'save'])
        world.session.pending = SimpleNamespace(operation='resume')
        with self.assertRaises(RuntimeError):
            subject.prepare_join_baseline(SimpleNamespace(tick=tick), world, time.monotonic()+2, Mock())

    def test_second_offer_requires_exact_confirmed_checkpoint_and_marker(self):
        _, checkpoint = self.make_world()
        ticket = {'checkpoint_id':checkpoint.checkpoint_id, 'sha256':checkpoint.sha256}
        subject.verify_join_offer(ticket, checkpoint.marker, checkpoint)
        for changed_ticket, marker in ((dict(ticket, checkpoint_id='other'), checkpoint.marker),
                                       (dict(ticket, sha256='d'*64), checkpoint.marker),
                                       (ticket, 'e'*32)):
            with self.assertRaises(ValueError): subject.verify_join_offer(changed_ticket, marker, checkpoint)

    def test_departure_pumps_eof_and_requires_fresh_marked_save(self):
        world, checkpoint = self.make_world()
        control = SimpleNamespace(_peers={'peer':object()})
        world.session.state = 'running'; world.session.players = ((1, 'client'),)
        calls = []
        def tick(_timeout):
            calls.append(1)
            if len(calls) == 1:
                control._peers.clear(); world.session.players = ()
                world.session.pending = SimpleNamespace(operation='pause')
            elif len(calls) == 2:
                world.session.state = 'saving'; world.session.pending = SimpleNamespace(operation='save')
            else:
                world.session.state = 'paused'; world.session.pending = None
        with patch.object(subject.recovery.tcp, 'await_eof') as eof, \
             patch.object(subject, 'verify_saved_marker', return_value=True) as verify:
            saved = subject.settle_departure(SimpleNamespace(tick=tick), world, control, 'peer',
                time.monotonic()+2, Mock(), {'checkpoint_id':'checkpoint-first'}, 'a'*32)
            eof.assert_called_once()
        self.assertEqual(saved, checkpoint)
        self.assertEqual(len(calls), 3)
        verify.assert_called_once()
        with self.assertRaises(RuntimeError):
            subject.settle_departure(Mock(), world, control, 'peer', time.monotonic()+2, Mock(),
                                     {'checkpoint_id':'checkpoint-first'}, 'a'*32)
        def drop(_timeout): control._peers.clear()
        with patch.object(subject.recovery.tcp, 'await_eof'):
            control._peers['peer'] = object()
            with self.assertRaises(ValueError):
                subject.settle_departure(SimpleNamespace(tick=drop), world, control, 'peer',
                    time.monotonic()+2, Mock(), {'checkpoint_id':checkpoint.checkpoint_id}, 'a'*32)
            world._offers.names.add('still-offered')
            control._peers['peer'] = object()
            with self.assertRaises(ValueError):
                subject.settle_departure(SimpleNamespace(tick=drop), world, control, 'peer',
                    time.monotonic()+2, Mock(), {'checkpoint_id':'checkpoint-first'}, 'a'*32)

    def test_all_diagnostic_cleanups_attempted_after_failure(self):
        first, second = Mock(), Mock()
        second.cleanup_diagnostic.side_effect = RuntimeError('unconfirmed')
        errors = []
        self.assertFalse(supervisor.cleanup_diagnostics([first, second], errors))
        first.cleanup_diagnostic.assert_called_once()
        second.cleanup_diagnostic.assert_called_once()
        self.assertTrue(errors)
        self.assertIsNone(supervisor.stop_owned_processes([], False, errors))

    def test_cancellation_interrupts_download_pump_and_enrollment(self):
        participant = subject.ServerClient(time.monotonic()+5, Path('/source'))
        def cancel(): raise InterruptedError('stop')
        participant.cancel_check = cancel
        try:
            with self.assertRaises(InterruptedError): participant.pump_loading()
            with self.assertRaises(InterruptedError): participant.enroll('a'*32, time.monotonic()+2)
            self.assertTrue(participant.fault)
        finally: participant.close()

    def test_guarded_enrollment_retains_lease_and_peer_validation(self):
        participant = subject.ServerClient(time.monotonic()+5, Path('/source'))
        participant.cancel_check = Mock()
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sender.bind(('127.0.0.1', 0))
            sender.sendto(b'not-a-hello', participant.sock.getsockname())
            sender.sendto(('HELLO|'+participant.lease+'|'+'a'*32).encode(), participant.sock.getsockname())
            participant.enroll('a'*32, time.monotonic()+2)
            self.assertEqual(participant.peer, sender.getsockname())
            self.assertGreaterEqual(participant.cancel_check.call_count, 4)
        finally: sender.close(); participant.close()

    def test_departure_fences_unverified_eof_marker_and_file_offer(self):
        world, checkpoint = self.make_world()
        control = SimpleNamespace(_peers={'peer':object()})
        ticket = {'checkpoint_id':'checkpoint-first'}
        host = SimpleNamespace(tick=lambda _timeout: control._peers.clear())
        with patch.object(subject.recovery.tcp, 'await_eof', side_effect=RuntimeError('no EOF')):
            with self.assertRaisesRegex(RuntimeError, 'no EOF'):
                subject.settle_departure(host, world, control, 'peer', time.monotonic()+2, Mock(), ticket, 'a'*32)
        self.assertIn('peer', control._peers)
        with patch.object(subject.recovery.tcp, 'await_eof'):
            with self.assertRaises(ValueError):
                subject.settle_departure(host, world, control, 'peer', time.monotonic()+2,
                                         Mock(), ticket, checkpoint.marker)
            control._peers['peer'] = object()
            world._offers.service.offered['name'] = object()
            with self.assertRaises(ValueError):
                subject.settle_departure(host, world, control, 'peer', time.monotonic()+2, Mock(), ticket, 'a'*32)
            world._offers.service.offered.clear()
            control._peers['peer'] = object()
            with patch.object(subject, 'verify_saved_marker', side_effect=ValueError('bad marker')):
                with self.assertRaisesRegex(ValueError, 'bad marker'):
                    subject.settle_departure(host, world, control, 'peer', time.monotonic()+2, Mock(), ticket, 'a'*32)

    def test_public_evidence_contains_only_expected_correlation_fields(self):
        ticket = dict(world_epoch='a'*32, connection_handle=1, baseline_id=2,
                      load_generation=3, checkpoint_id='checkpoint-'+'b'*32,
                      sha256='c'*64, attempt_id='d'*32, slot='save_009')
        result = {}
        subject.record_client_evidence(result, ticket, 'e'*32, (123, 456), (124, 457))
        self.assertEqual(result['client_ticket'], ticket)
        self.assertEqual(result['client_checkpoint_sha256'], ticket['sha256'])
        self.assertEqual(result['client_loaded_marker'], 'e'*32)
        self.assertTrue(result['client_owned_process_stopped'])
        self.assertEqual((result['client_x4_pid'], result['client_x4_start_ticks']), (123, 456))
        self.assertEqual((result['server_x4_pid'], result['server_x4_start_ticks']), (124, 457))
        self.assertFalse(any('lease' in field or 'token' in field for field in result))
        with self.assertRaises(ValueError):
            subject.record_client_evidence({}, dict(ticket, file_token='secret'), 'e'*32, (123, 456), (124, 457))
        with self.assertRaises(ValueError):
            subject.record_client_evidence({}, ticket, 'e'*32, (123, 456), (123, 456))

    def test_recovered_watch_not_pair_runner_server_log_path_is_used(self):
        participant = subject.ServerClient(time.monotonic()+20, Path('/source'))
        watch = SimpleNamespace(stage=3, poll=Mock(return_value=True))
        participant.recovery_watch = watch
        try:
            with patch.object(subject.recovery, 'check_client_log') as client_log:
                participant.verify_logs(Path('/nonexistent/pair/server.log'), Path('/client.log'),
                                        {'ticket':'value'}, 'marker')
            self.assertEqual(watch.poll.call_count, 2)
            client_log.assert_called_once_with(Path('/client.log'), {'ticket':'value'}, 'marker')
        finally:
            participant.close()

    def test_diagnostic_cleanup_reaps_helpers_without_closing_server_control(self):
        participant = subject.ServerClient(time.monotonic()+20, Path('/source'))
        helper, control = Mock(), Mock()
        participant.helpers.append(helper); participant.control = control
        self.assertTrue(participant.cleanup_diagnostic())
        helper.stop.assert_called_once_with()
        control.close.assert_not_called()

    def test_uncertain_helper_cleanup_is_failure_and_keeps_server_control(self):
        participant = subject.ServerClient(time.monotonic()+20, Path('/source'))
        helper, control = Mock(), Mock()
        helper.stop.side_effect = RuntimeError('uncertain')
        participant.helpers.append(helper); participant.control = control
        with self.assertRaises(RuntimeError): participant.cleanup_diagnostic()
        control.close.assert_not_called()


if __name__ == '__main__':
    unittest.main()
