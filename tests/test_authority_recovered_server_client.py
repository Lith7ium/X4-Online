"""Offline ownership and evidence checks; no X4 process is started."""
from pathlib import Path
import hashlib
import json
import tempfile
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
    def test_witness_guard_pump_switch_fences_tcp_lease_and_never_pumps_after_switch(self):
        participant=SimpleNamespace(pump_loading=Mock())
        owner=subject.WitnessGuardPump(participant,time.monotonic()+5)
        owner();participant.pump_loading.assert_called_once()
        lease=object();control=SimpleNamespace(_reader_lease=lease)
        host=SimpleNamespace(_control=control,_busy=True)
        active=Mock(return_value=True);owner.activate(host=host,guard=active)
        owner();active.assert_called_once();participant.pump_loading.assert_called_once()
        with self.assertRaises(RuntimeError):owner.activate(host=host,guard=active)
        self.assertEqual(owner.phase,'failed')
        owner=subject.WitnessGuardPump(participant,time.monotonic()+5)
        def change():control._reader_lease=object();return True
        owner.activate(host=host,guard=change)
        with self.assertRaises(RuntimeError):owner()
        self.assertEqual(owner.phase,'failed')

    def test_witness_guard_pump_reentry_is_permanently_fatal(self):
        participant=SimpleNamespace(pump_loading=Mock())
        owner=subject.WitnessGuardPump(participant,time.monotonic()+5)
        def reenter():
            try:owner()
            except RuntimeError:pass
            return True
        host=SimpleNamespace(_control=SimpleNamespace(_reader_lease=None,_reader_free=Mock()),_busy=False)
        owner.activate(host=host,guard=reenter)
        with self.assertRaises(RuntimeError):owner()
        self.assertEqual(owner.phase,'failed');participant.pump_loading.assert_not_called()

    def test_witness_guard_blocks_even_transient_tcp_poll_when_reader_was_free(self):
        from authority.experimental_tcp_control import ExperimentalTCPControl
        control=object.__new__(ExperimentalTCPControl)
        control._thread=threading.get_ident();control._failed=False;control._closed=False
        control._reader_lease=None;control._latest_motion=None;control._peers={}
        host=SimpleNamespace(_control=control,_busy=False)
        owner=subject.WitnessGuardPump(SimpleNamespace(pump_loading=Mock()),time.monotonic()+5)
        def illegally_poll():control.poll(0);return True
        owner.activate(host=host,guard=illegally_poll)
        with self.assertRaisesRegex(RuntimeError,'leased'):owner()
        self.assertEqual(owner.phase,'failed');self.assertIsNone(control._reader_lease);self.assertFalse(host._busy)

    def test_witness_guard_refuses_control_owner_replacement(self):
        control=SimpleNamespace(_reader_lease=None,_reader_free=Mock())
        host=SimpleNamespace(_control=control,_busy=False)
        owner=subject.WitnessGuardPump(SimpleNamespace(pump_loading=Mock()),time.monotonic()+5)
        def replace():host._control=object();return True
        owner.activate(host=host,guard=replace)
        with self.assertRaisesRegex(RuntimeError,'TCP ownership'):owner()
        self.assertIsNone(control._reader_lease);self.assertFalse(host._busy)

    def test_witness_guard_prepared_during_retained_admission_and_registered_for_cleanup(self):
        participant=SimpleNamespace(keep_worker=True,pump_loading=Mock(),helpers=[])
        world,checkpoint=self.make_world();check=Mock()
        guard=SimpleNamespace(check=Mock(return_value=True),status=('ready','a'*32,2,'b'*64),_cleanup=Mock())
        def make_guard(store,baseline,**kwargs):
            self.assertIs(store,world._store);self.assertIs(baseline,checkpoint)
            kwargs['pump']();self.assertIs(kwargs['registry'],participant.helpers)
            return guard
        with patch('authority_witness_guard_client.WitnessGuardClient',side_effect=make_guard):
            actual,pump=subject.prepare_witness_guard(participant,world,checkpoint,time.monotonic()+5,check)
        self.assertIs(actual,guard);self.assertEqual(pump.phase,'admission')
        self.assertEqual(participant.guard_resources,[guard]);guard.check.assert_called_once()
        participant.pump_loading.assert_called_once();self.assertEqual(check.call_count,2)
        participant.keep_worker=False
        with self.assertRaises(ValueError):subject.prepare_witness_guard(participant,world,checkpoint,time.monotonic()+5,check)

    def test_guard_initialization_pumps_actual_tcp_keepalive(self):
        import authority_witness_guard_client as client
        import test_authority_experimental_tcp_participants as fixture
        from authority.experimental_tcp_control import offer_request
        case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation');case.setUp()
        guard=None
        try:
            case.control._keepalive_enabled=True
            conn=case.connect();case.host.tick();conn.sendall(offer_request());case.host.tick(.1);case.host.tick(.1)
            conn.recv(8192)
            peer=next(iter(case.control._peers.values()));self.assertEqual(peer['stage'],'offered')
            conn.sendall(json.dumps({'version':1,'kind':'keepalive','attempt_id':peer['attempt_id'],'sequence':1}).encode()+b'\n')
            participant=SimpleNamespace(keep_worker=True,pump_loading=lambda:case.control.poll(0),helpers=[])
            checkpoint=SimpleNamespace(checkpoint_id='checkpoint-'+('a'*32),path=Path('/tmp/not-read'),
                                       sha256='b'*64,size=1,marker='c'*32)
            script=Path(case.temp.name)/'guard.py'
            script.write_text('''import json,socket,sys,time
s=socket.socket(fileno=int(sys.argv[1]));f=s.makefile('rb');c=json.loads(f.readline());time.sleep(.15)
s.sendall((json.dumps(dict(token=c['token'],seq=0,event='READY',status=['ready','a'*32,2,'b'*64]))+'\\n').encode())
r=json.loads(f.readline());s.sendall((json.dumps(dict(token=c['token'],seq=r['seq'],event='CHECKED'))+'\\n').encode());time.sleep(10)
''')
            with patch.object(client,'READER',script):
                guard,_=subject.prepare_witness_guard(participant,case.world,checkpoint,time.monotonic()+4,lambda:None)
            self.assertEqual(peer['keepalive_sequence'],1)
            conn.settimeout(1);self.assertEqual(json.loads(conn.recv(8192))['kind'],'alive')
        finally:
            if guard:guard._cleanup()
            case.doCleanups()

    def test_witness_join_explicitly_enables_registry_observation(self):
        self.assertFalse(subject.client_registry_enabled(SimpleNamespace()))
        self.assertTrue(subject.client_registry_enabled(SimpleNamespace(registry_witness_join=True)))
        self.assertFalse(subject.client_registry_enabled(SimpleNamespace(registry_witness_join=1)))

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

    def test_overlap_guards_other_client_while_each_is_finalized(self):
        active=[]; events=[]
        world=SimpleNamespace(session=SimpleNamespace(state='running', pending=None, players=((1,'a'),(2,'b')),
                                                      ready_players=((1,'a'),(2,'b'))))
        control=SimpleNamespace(_peers={'a':object(),'b':object()})
        def verify():
            events.append(('verify', tuple(a.participant.server_tcp for a in active)))
        def start(index):
            peer=('a','b')[index]
            def finish():
                events.append(('finish',peer,tuple(a.participant.server_tcp for a in active)))
                verify()
                return {'client_ticket':{'checkpoint_id':'old'}, 'client_loaded_marker':'a'*32,
                        'server_x4_pid':10, 'server_x4_start_ticks':11,
                        'client_x4_pid':20+index, 'client_x4_start_ticks':21+index}
            return subject.ActiveClient(SimpleNamespace(server_tcp=peer),{},finish)
        def tick(_timeout):
            control._peers.pop('a'); world.session.players=((2,'b'),); world.session.ready_players=((2,'b'),)
        host=SimpleNamespace(tick=tick)
        checkpoint=SimpleNamespace(checkpoint_id='new',sha256='b'*64,marker='c'*32)
        def observe(_deadline, _tick, check):
            events.append(('clock',tuple(a.participant.server_tcp for a in active)))
            check()
            return {'server_game_time_before':1.0,'server_game_time_after':2.0}
        clock=SimpleNamespace(observe=observe)
        with patch.object(subject.recovery.tcp,'await_eof') as eof, \
             patch.object(subject,'settle_departure',return_value=checkpoint) as settle:
            result=supervisor.run_overlapping_diagnostics(start=start,active_clients=active,world=world,
                host=host,control=control,deadline=time.monotonic()+2,verify=verify,clock=clock)
        self.assertTrue(result['diagnostic_overlap_confirmed'])
        self.assertTrue(result['diagnostic_remaining_session_running'])
        self.assertEqual(result['diagnostic_overlap_clients'][1]['departure_checkpoint_id'],'new')
        self.assertIn(('finish','a',('b',)),events)
        self.assertIn(('finish','b',()),events)
        self.assertIn(('clock',('b',)),events)
        self.assertLess(events.index(('finish','a',('b',))),events.index(('clock',('b',))))
        self.assertLess(events.index(('clock',('b',))),events.index(('finish','b',())))
        self.assertEqual(result['diagnostic_remaining_server_clock']['server_game_time_after'],2.0)
        self.assertEqual(active,[])
        eof.assert_called_once(); settle.assert_called_once()

    def test_overlap_guard_hashes_each_save_across_boundaries_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=[Path(tmp)/name for name in ('server','client-1','client-2')]
            for path in paths: path.write_bytes(path.name.encode())
            expected={path:hashlib.sha256(path.read_bytes()).digest() for path in paths}
            calls=[]; events=[]
            def check_file(path):
                calls.append(path)
                if hashlib.sha256(path.read_bytes()).digest() != expected[path]:
                    raise ValueError('protected save changed')
            def check_client(path, *, server_checked):
                self.assertTrue(server_checked)
                check_file(path); check_file(path)
            active=[SimpleNamespace(participant=SimpleNamespace(
                        check_active=lambda *, server_checked, path=path:check_client(path,server_checked=server_checked)))
                    for path in paths[1:]]
            def guard():
                supervisor.verify_diagnostic_context(verify_server=lambda:check_file(paths[0]),
                    active_clients=active,check_process=lambda:events.append('process'),
                    check_cancel=lambda:events.append('cancel'))
            guard()
            self.assertEqual(calls,[paths[0],paths[1],paths[1],paths[0],paths[2],paths[2],paths[0]])
            self.assertEqual(events,['cancel','process','cancel'])
            paths[1].write_bytes(b'changed')
            operation=Mock()
            with self.assertRaisesRegex(ValueError,'protected save changed'):
                guard(); operation()
            operation.assert_not_called()
            active[0].participant.check_active=Mock(side_effect=RuntimeError('worker exited'))
            with self.assertRaisesRegex(RuntimeError,'worker exited'):
                guard(); operation()
            operation.assert_not_called()

    def test_overlap_failure_leaves_all_started_clients_for_fencing(self):
        active=[]; owners=[Mock(),Mock()]
        first=SimpleNamespace(participant=owners[0],finish=Mock())
        second=SimpleNamespace(participant=owners[1],finish=Mock())
        started=[first,second]
        def start(index): return started[index]
        checks=0
        def verify():
            nonlocal checks
            checks+=1
            if checks==2: raise RuntimeError('protected context changed')
        world=SimpleNamespace(session=SimpleNamespace(state='running',players=((1,'a'),(2,'b')),
                                                     ready_players=((1,'a'),(2,'b'))))
        with self.assertRaisesRegex(RuntimeError,'protected context changed'):
            supervisor.run_overlapping_diagnostics(start=start,active_clients=active,world=world,
                host=Mock(),control=Mock(),deadline=time.monotonic()+2,verify=verify)
        self.assertEqual(active,[first,second])
        first.finish.assert_not_called(); second.finish.assert_not_called()
        self.assertTrue(supervisor.cleanup_diagnostics(owners,[]))
        owners[0].cleanup_diagnostic.assert_called_once(); owners[1].cleanup_diagnostic.assert_called_once()

    def test_overlap_requires_three_distinct_correlated_x4_processes(self):
        first={'server_x4_pid':10,'server_x4_start_ticks':11,
               'client_x4_pid':20,'client_x4_start_ticks':21}
        second=dict(first,client_x4_pid=30,client_x4_start_ticks=31)
        supervisor.validate_overlap_identities(first,second)
        for invalid in (dict(first), dict(second,server_x4_pid=12),
                        dict(second,client_x4_pid=10,client_x4_start_ticks=11),
                        dict(second,client_x4_pid=True)):
            with self.assertRaises(ValueError): supervisor.validate_overlap_identities(first,invalid)

    def test_active_finalization_is_never_retried_after_partial_failure(self):
        finish=Mock(side_effect=RuntimeError('uncertain cleanup'))
        active=subject.ActiveClient(Mock(),{},finish)
        with self.assertRaisesRegex(RuntimeError,'uncertain cleanup'): active.finish()
        with self.assertRaisesRegex(RuntimeError,'already finalized'): active.finish()
        finish.assert_called_once()

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
