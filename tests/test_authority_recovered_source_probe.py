"""Source probe lifecycle and explicit evidence scope; no X4 or sockets."""
from pathlib import Path
from contextlib import contextmanager
import os
import socket
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_recovered_source_probe as subject
import authority_recovered_server_client as recovered_client
import authority_recovered_loopback_server as supervisor
from authority.experimental_tcp_motion import motion_digest
import linux_gate_live


def cleanup_motion_fixture(case):
    """Propagate nested unittest cleanup and client-thread failures outward."""
    errors = []
    for name, action, returns_status in (
            ('client threads', case.finish, False),
            ('participant fixture', case.case.doCleanups, True),
            ('motion fixture', case.doCleanups, True)):
        try:
            result = action()
            if returns_status and result is not True:
                raise AssertionError(name + ' cleanup failed')
        except BaseException as error:
            errors.append(error)
    if errors:
        raise BaseExceptionGroup('nested motion fixture cleanup failed', errors)


class Probe(unittest.TestCase):
    def test_latest_diagnostic_snapshot_retains_partial_progress_without_changing_legacy(self):
        legacy = subject.SourceProbeDiagnostics()
        legacy.samples_received = 2
        legacy.confirmed_client_receipts = 2
        legacy.pull_attempts = 3
        legacy.empty_pulls = 1
        legacy.last_pull_seconds = .7
        snapshot = legacy.snapshot()
        expected = {'samples_received': 2, 'confirmed_client_receipts': 2,
                    'pull_attempts': 3, 'empty_pulls': 1, 'last_pull_seconds': .7}
        self.assertEqual({key: snapshot[key] for key in expected}, expected)
        self.assertNotIn('latest_collection', snapshot)

        diagnostics = subject.SourceProbeDiagnostics()
        diagnostics.latest_collection = {}
        initial = diagnostics.snapshot()
        for key in ('samples_received', 'confirmed_client_receipts', 'pull_attempts'):
            self.assertEqual(initial[key], 0)
        self.assertIsNone(initial['last_pull_seconds'])
        diagnostics.latest_collection = {
            'state': 'failed', 'queued_sequences': [1, 2, 3], 'acknowledged_sequences': [1],
            'stats': {'operations': {'begin': {'calls': 4}}, 'empty_pulls': 1,
                      'sample_times': [{'sequence': 3, 'pull_elapsed_seconds': .12}]}}
        partial = diagnostics.snapshot()
        self.assertEqual(partial['samples_received'], 3)
        self.assertEqual(partial['confirmed_client_receipts'], 1)
        self.assertEqual(partial['pull_attempts'], 4)
        self.assertEqual(partial['empty_pulls'], 1)
        self.assertEqual(partial['last_pull_seconds'], .12)
        partial['latest_collection']['queued_sequences'].append(4)
        partial['latest_collection']['stats']['operations']['begin']['calls'] = 99
        partial['latest_collection']['stats']['sample_times'][0]['pull_elapsed_seconds'] = 99
        retained = diagnostics.snapshot()
        self.assertEqual(retained['samples_received'], 3)
        self.assertEqual(retained['pull_attempts'], 4)
        self.assertEqual(retained['last_pull_seconds'], .12)
        self.assertEqual(diagnostics.samples_received, 0)
        self.assertEqual(diagnostics.confirmed_client_receipts, 0)
        self.assertEqual(diagnostics.pull_attempts, 0)

        diagnostics.latest_collection = {
            'queued_samples': [{'sequence': 1}, {'sequence': 2}, {'sequence': 3}],
            'acknowledged_samples': [{'sequence': 1}, {'sequence': 3}],
            'stats': {'operations': {'begin': {'calls': 3}},
                      'sample_times': [{'sequence': 3, 'pull_elapsed_seconds': .08}]}}
        complete = diagnostics.snapshot()
        self.assertEqual(complete['samples_received'], 3)
        self.assertEqual(complete['confirmed_client_receipts'], 2)
        self.assertEqual(complete['pull_attempts'], 3)
        self.assertEqual(complete['last_pull_seconds'], .08)

    def test_saved_apply_preflight_and_durable_intent_order(self):
        for outcome in ('near', 'ready', 'far', 'intent_error', 'apply_error'):
            with self.subTest(outcome=outcome):
                events=[]
                def preflight(sample):
                    events.append('preflight')
                    return 'ready' if outcome in ('ready','intent_error','apply_error') else outcome
                def intent(sample):
                    events.append('intent')
                    if outcome=='intent_error': raise OSError('fsync failed')
                    return True
                def apply(sample):
                    events.append('apply')
                    if outcome=='apply_error': raise RuntimeError('receipt lost')
                    return True
                source=SimpleNamespace(preflight=preflight,apply_once=apply)
                with patch.object(subject.time,'monotonic',return_value=15):
                    call=lambda: subject.perform_saved_apply(source,{'index':1318},10,
                        active_guard=lambda: events.append('guard'),
                        checked_operation=lambda f,*a: f(*a),record_apply_intent=intent)
                    if outcome in ('far','intent_error','apply_error'):
                        with self.assertRaises((RuntimeError,OSError)): call()
                    else:
                        result=call()
                        self.assertEqual(result['apply_requested'],outcome=='ready')
                        if outcome=='ready': self.assertEqual(result['host_receipt_to_apply_seconds_lower_bound'],5)
                self.assertEqual(events.count('preflight'),1)
                self.assertEqual(events.count('intent'),int(outcome in ('ready','intent_error','apply_error')))
                self.assertEqual(events.count('apply'),int(outcome in ('ready','apply_error')))
                if 'apply' in events: self.assertLess(events.index('intent'),events.index('apply'))

    def test_saved_apply_refuses_unpinned_context_before_binding(self):
        for fixture, callback in (('recovery_enh_870', lambda _: True),
                                  ('unknown', lambda _: True), (None, lambda _: True)):
            with self.subTest(fixture=fixture):
                events, kwargs, _ = self.context()
                kwargs.update(saved_apply_fixture=fixture,record_apply_intent=callback)
                with self.assertRaises(ValueError): subject.run(**kwargs)
                self.assertEqual(events,[])

    def test_nested_fixture_cleanup_failures_propagate(self):
        inner = SimpleNamespace(doCleanups=Mock(return_value=False))
        case = SimpleNamespace(case=inner, finish=Mock(side_effect=AssertionError('client thread failed')),
                               doCleanups=Mock(return_value=True))
        with self.assertRaises(BaseExceptionGroup) as caught:
            cleanup_motion_fixture(case)
        self.assertEqual(len(caught.exception.exceptions), 2)
        case.finish.assert_called_once();inner.doCleanups.assert_called_once();case.doCleanups.assert_called_once()

    def test_local_pair_must_match_the_explicit_source_before_binding(self):
        for pair in ({'nonce': 'f' * 32, 'index': 2},
                     {'nonce': 'invalid', 'index': 1},
                     {'nonce': 'f' * 32, 'index': True},
                     {'nonce': 'f' * 32, 'index': 1, 'delivery': False},
                     {'nonce': 'f' * 32, 'index': 1, 'delivery': True}):
            with self.subTest(pair=pair):
                events, kwargs, _ = self.context()
                kwargs['settings']['local_pair'] = pair
                with self.assertRaisesRegex(ValueError, 'local pair'):
                    subject.run(**kwargs)
                self.assertEqual(events, [])

    def context(self, stop=True):
        events=[];baseline=object();settings={'epoch':'a'*32,'baseline':2,'lease':'b'*32,'attempt':'c'*32,'generation':'d'*32}
        world=SimpleNamespace(session=SimpleNamespace(state='running',pending=None,baseline_id=None),_baseline=(7,baseline))
        guard=SimpleNamespace(status=('ready','a'*32,2,'e'*64),deadline=time.monotonic()+100,check=Mock(return_value=True),
            stop=Mock(side_effect=lambda:events.append('guard_stop') or True))
        pump=SimpleNamespace(activate=Mock(side_effect=lambda **kw:events.append('pump_active')))
        active=SimpleNamespace(participant=SimpleNamespace(check_active=Mock(return_value=True)))
        def sample(seq):return {'index':1,'sequence':seq,'sector_macro':'test','source_time':seq,
            'x':0,'y':0,'z':0,'velocity':None,'epoch':'a'*32,'generation':'d'*32}
        samples=iter([sample(1),sample(2)])
        class Source:
            def request_candidate(self):events.append('candidate');return 1
            def register_saved(self,index):events.append(('register',index))
            def pull(self):events.append('pull');self.capture(next(samples))
            def stop_remote(self):events.append('source_stop');return stop
            def close(self):events.append('close')
        source=Source()
        def bind(sock,motion,**kwargs):
            self.assertEqual(kwargs['select_recipients']({},[]),[])
            self.assertTrue(kwargs['saved_guard']('a'*32,2));source.capture=kwargs['validate_sample'];events.append('bind')
            return source
        kwargs=dict(sock=object(),settings=settings,index=1,baseline=baseline,guard=guard,pump=pump,
            active=active,host=object(),world=world,identity=(1,2),verify=Mock(),verify_process=Mock())
        return events,kwargs,bind
    def test_two_samples_stop_then_guard_shutdown(self):
        events,kwargs,bind=self.context()
        diagnostics=subject.SourceProbeDiagnostics();kwargs['diagnostics']=diagnostics
        with patch.object(subject,'ExperimentalTCPJobDelivery'),patch.object(subject,'ExperimentalTCPMotion'), \
             patch.object(subject,'bind_running_source_motion',side_effect=bind),patch.object(subject.os,'stat',return_value=SimpleNamespace(st_dev=1,st_ino=2)),patch.object(subject.time,'sleep'):
            result=subject.run(**kwargs)
        self.assertEqual(events,['pump_active','bind',('register',1),'pull','pull','source_stop','guard_stop','close'])
        self.assertEqual(len(result['samples']),2);self.assertFalse(result['client_motion_proven'])
        self.assertFalse(result['cross_process_identity_proven'])
        self.assertNotIn('generation',result['samples'][0]);self.assertNotIn('epoch',result['samples'][0])
        self.assertEqual(diagnostics.snapshot()['phase'],'complete')
        self.assertEqual(diagnostics.snapshot()['samples_received'],2)
        self.assertEqual(diagnostics.snapshot()['saved_checkpoint_guard_calls'],1)
        self.assertEqual(diagnostics.snapshot()['pull_attempts'],2)
        self.assertEqual(diagnostics.snapshot()['prevalidated_samples'],2)
        self.assertEqual(diagnostics.snapshot()['confirmed_client_receipts'],0)

    def test_opt_in_guard_callsites_preserve_operations_and_measure_failures(self):
        event_sequences = []
        for enabled in (False, True):
            events, kwargs, bind = self.context()
            clock = [1.0]
            kwargs['guard'].deadline = 1000
            diagnostics = subject.SourceProbeDiagnostics(include_guard_callsites=enabled)
            kwargs['diagnostics'] = diagnostics
            def verify():
                events.append('verify')
                clock[0] += 2
            def checkpoint_guard():
                events.append('checkpoint')
                clock[0] += 3
                return True
            kwargs['verify'] = verify
            kwargs['guard'].check.side_effect = checkpoint_guard
            with patch.object(subject.time, 'monotonic', side_effect=lambda: clock[0]), \
                 patch.object(subject.time, 'sleep'), patch.object(subject, 'ExperimentalTCPJobDelivery'), \
                 patch.object(subject, 'ExperimentalTCPMotion'), \
                 patch.object(subject, 'bind_running_source_motion', side_effect=bind), \
                 patch.object(subject.os, 'stat', return_value=SimpleNamespace(st_dev=1, st_ino=2)):
                subject.run(**kwargs)
            progress = diagnostics.snapshot()
            event_sequences.append(events)
            if not enabled:
                self.assertNotIn('guard_call_sites', progress)
                continue
            rows = progress['guard_call_sites']
            self.assertEqual(progress['guard_call_sites_dropped'], 0)
            for kind, count, seconds in (
                    ('full', progress['full_guard_calls'], progress['full_guard_seconds']),
                    ('saved_checkpoint', progress['saved_checkpoint_guard_calls'],
                     progress['saved_checkpoint_guard_seconds'])):
                matches = [row for row in rows if row['guard'] == kind]
                self.assertEqual(sum(row['calls'] for row in matches), count)
                self.assertEqual(sum(row['seconds'] for row in matches), seconds)
                self.assertTrue(all(row['stack'] and row['phase'] for row in matches))
            self.assertTrue(any(row['phase'] == 'bind_source' and row['guard'] == 'saved_checkpoint'
                                for row in rows))
            self.assertNotIn('lease', repr(rows))
        self.assertEqual(event_sequences[0], event_sequences[1])

        _, kwargs, _ = self.context()
        diagnostics = subject.SourceProbeDiagnostics(include_guard_callsites=True)
        kwargs['diagnostics'] = diagnostics
        kwargs['verify'] = Mock(side_effect=RuntimeError('guard failure'))
        with self.assertRaisesRegex(RuntimeError, 'guard failure'):
            subject.run(**kwargs)
        self.assertEqual(diagnostics.snapshot()['guard_call_sites'][0]['guard'], 'full')

    def test_guard_callsite_capacity_is_bounded(self):
        diagnostics = subject.SourceProbeDiagnostics(include_guard_callsites=True)
        for line in range(diagnostics._MAX_CALL_SITES + 3):
            diagnostics.record_guard_call('full', ('phase', (('file', 'call', line),)), 1)
        progress = diagnostics.snapshot()
        self.assertEqual(len(progress['guard_call_sites']), diagnostics._MAX_CALL_SITES)
        self.assertEqual(progress['guard_call_sites_dropped'], 3)
    def test_unconfirmed_source_stop_never_closes_or_authorizes_guard_shutdown(self):
        events,kwargs,bind=self.context(stop=False)
        with patch.object(subject,'ExperimentalTCPJobDelivery'),patch.object(subject,'ExperimentalTCPMotion'), \
             patch.object(subject,'bind_running_source_motion',side_effect=bind),patch.object(subject.os,'stat',return_value=SimpleNamespace(st_dev=1,st_ino=2)),patch.object(subject.time,'sleep'):
            with self.assertRaises(RuntimeError):subject.run(**kwargs)
        self.assertNotIn('close',events);self.assertNotIn('guard_stop',events)
    def test_candidate_request_precedes_register_and_is_not_a_reservation(self):
        events,kwargs,bind=self.context();kwargs['index']=None;kwargs['candidate_indices']=(1,2)
        with patch.object(subject,'ExperimentalTCPJobDelivery'),patch.object(subject,'ExperimentalTCPMotion'), \
             patch.object(subject,'bind_running_source_motion',side_effect=bind),patch.object(subject.os,'stat',return_value=SimpleNamespace(st_dev=1,st_ino=2)),patch.object(subject.time,'sleep'):
            result=subject.run(**kwargs)
        self.assertLess(events.index('candidate'),events.index(('register',1)))
        self.assertTrue(result['candidate_selected']);self.assertFalse(result['candidate_is_reservation'])
    def test_out_of_range_or_wrong_registry_refused_before_binding(self):
        for change in ('index','status'):
            events,kwargs,bind=self.context()
            if change=='index':kwargs['index']=3
            else:kwargs['guard'].status=('ready','f'*32,2,'e'*64)
            with self.assertRaises(ValueError):subject.run(**kwargs)
            self.assertEqual(events,[])
    def test_overall_deadline_stops_before_binding(self):
        events,kwargs,bind=self.context();kwargs['guard'].deadline=0
        with self.assertRaises(TimeoutError):subject.run(**kwargs)
        self.assertNotIn('bind',events);self.assertNotIn('source_stop',events)

    def test_deadline_is_rechecked_after_synchronous_verification(self):
        events,kwargs,bind=self.context();clock=[1.0];kwargs['guard'].deadline=1000
        kwargs['verify']=lambda:clock.__setitem__(0,92.0)
        with patch.object(subject.time,'monotonic',side_effect=lambda:clock[0]):
            with self.assertRaises(TimeoutError):subject.run(**kwargs)
        self.assertNotIn('bind',events);self.assertNotIn('source_stop',events)

    def test_pull_diagnostics_distinguish_empty_and_unfinished_sample(self):
        for mode in ('empty_then_complete', 'sample_then_failure'):
            with self.subTest(mode=mode):
                _, kwargs, original_bind = self.context()
                clock = [1.0]
                kwargs['guard'].deadline = 1000
                diagnostics = subject.SourceProbeDiagnostics()
                kwargs['diagnostics'] = diagnostics

                def bind(sock, motion, **options):
                    source = original_bind(sock, motion, **options)
                    original_pull = source.pull
                    pull_count = [0]

                    def pull():
                        pull_count[0] += 1
                        clock[0] += 10
                        if pull_count[0] == 1 and mode == 'empty_then_complete':
                            return None
                        original_pull()
                        if mode == 'sample_then_failure':
                            raise RuntimeError('simulated failure after validation')

                    source.pull = pull
                    return source

                with patch.object(subject.time, 'monotonic', side_effect=lambda: clock[0]), \
                     patch.object(subject.time, 'sleep'), patch.object(subject, 'ExperimentalTCPJobDelivery'), \
                     patch.object(subject, 'ExperimentalTCPMotion'), \
                     patch.object(subject, 'bind_running_source_motion', side_effect=bind), \
                     patch.object(subject.os, 'stat', return_value=SimpleNamespace(st_dev=1, st_ino=2)):
                    if mode == 'sample_then_failure':
                        with self.assertRaisesRegex(RuntimeError, 'simulated failure'):
                            subject.run(**kwargs)
                    else:
                        subject.run(**kwargs)
                progress = diagnostics.snapshot()
                self.assertEqual(progress['last_pull_seconds'], 10)
                self.assertEqual(progress['confirmed_client_receipts'], 0)
                if mode == 'sample_then_failure':
                    self.assertEqual(progress['pull_attempts'], 1)
                    self.assertEqual(progress['empty_pulls'], 0)
                    self.assertEqual(progress['prevalidated_samples'], 1)
                    self.assertEqual(progress['samples_received'], 0)
                else:
                    self.assertEqual(progress['pull_attempts'], 3)
                    self.assertEqual(progress['empty_pulls'], 1)
                    self.assertEqual(progress['prevalidated_samples'], 2)
                    self.assertEqual(progress['samples_received'], 2)

    def test_supervisor_retains_timeout_phase_and_guard_cost_without_secrets(self):
        events, kwargs, _ = self.context()
        clock = [1.0]
        kwargs['guard'].deadline = 1000
        verification_calls = []
        def verify():
            verification_calls.append(True)
            if len(verification_calls) == 2:
                clock[0] = 92.0
        def bind(_sock, _motion, **options):
            options['client_guard']()
            raise AssertionError('expired guard returned')
        kwargs['verify'] = verify
        result = {}
        with patch.object(subject.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(subject, 'ExperimentalTCPJobDelivery'), patch.object(subject, 'ExperimentalTCPMotion'), \
             patch.object(subject, 'bind_running_source_motion', side_effect=bind), \
             patch.object(subject.os, 'stat', return_value=SimpleNamespace(st_dev=1, st_ino=2)):
            with self.assertRaisesRegex(TimeoutError, 'source diagnostic deadline'):
                supervisor.run_source_probe_with_progress(result, subject.run, **kwargs)
        progress = result['source_diagnostic_progress']
        self.assertEqual(progress['phase'], 'bind_source')
        self.assertEqual(progress['full_guard_calls'], 2)
        self.assertEqual(progress['full_guard_seconds'], 91.0)
        self.assertEqual(progress['phase_seconds']['bind_source'], 91.0)
        self.assertEqual(progress['samples_received'], 0)
        self.assertEqual(len(verification_calls), 2)
        self.assertNotIn('source_stop', events)
        self.assertNotIn('a'*32, str(progress))

    def test_extended_diagnostic_timeouts_preserve_sequence_and_fences(self):
        for mode in ('complete', 'deadline', 'idle_fence', 'bad_order', 'wrong_client_timeout',
                     'changed_client_timeout', 'changed_client_socket', 'wrong_sent_timeout',
                     'long_complete', 'long_deadline', 'long_bad_order', 'long_delivery_failure'):
            with self.subTest(mode=mode):
                events, kwargs, _ = self.context()
                clock = [1.0]
                long_mode = mode.startswith('long_')
                kwargs['guard'].deadline = 3000 if long_mode else 1000
                def slow_saved_guard():
                    clock[0] += 10
                    return True
                kwargs['guard'].check = Mock(side_effect=slow_saved_guard)
                kwargs['client_motion'] = True
                kwargs['verify_stopped'] = Mock()
                kwargs['index'] = None
                kwargs['candidate_indices'] = (1, 2)
                kwargs['diagnostic_timeouts'] = {
                    'total': 600, 'source_bind_stage': 120, 'source_operation': 300,
                    'tcp_send': 240, 'client_bind': 25,
                }
                if long_mode:
                    kwargs['private_long_diagnostic'] = True
                    kwargs['diagnostic_timeouts'].update(total=2400, source_operation=600, tcp_send=480)
                if mode in ('bad_order', 'long_bad_order'):
                    kwargs['diagnostic_timeouts']['tcp_send'] = 25
                kwargs['world'].session.players = kwargs['world'].session.ready_players = ((1, 'one'),)
                peer = {'stage': 'admitted', 'deadline': None}
                tcp = object()
                kwargs['host'] = SimpleNamespace(_control=SimpleNamespace(_peers={tcp: peer}))
                kwargs['active'].participant.server_tcp = tcp
                kwargs['active'].participant.motion_worker_config = {'timeout': 24 if mode == 'wrong_client_timeout' else 25}
                kwargs['active'].participant._motion_worker_timeout_snapshot = 24 if mode == 'wrong_sent_timeout' else 25
                selected = {'id': 'peer_1', 'incarnation': 'f'*32}
                class Delivery:
                    def __init__(self, _host, *, enabled, timeout, **options):
                        self_test.assertTrue(enabled)
                        self_test.assertEqual(timeout, 480 if long_mode else 240)
                        self_test.assertEqual(options, {'private_long_diagnostic': True} if long_mode else {})
                    def membership(self): return (selected,)
                class Motion:
                    def __init__(self, *_args, **_kwargs): self._tracks = {}
                class Sock:
                    def getsockname(self): return ('127.0.0.1', 1)
                    def getpeername(self): return ('127.0.0.1', 2)
                    def fileno(self): return 99
                kwargs['sock'] = Sock()
                class Source:
                    state = 'ready'
                    sequence = 0
                    def checked(self):
                        self_test.assertTrue(self.client_guard())
                        self_test.assertTrue(self.saved_guard('a'*32, 2))
                    def request_candidate(self):
                        events.append('candidate')
                        self.checked()
                        clock[0] += 10
                        if mode in ('deadline', 'long_deadline'):
                            clock[0] = 2401 if long_mode else 601
                        if mode == 'idle_fence': peer['deadline'] = clock[0] + 300
                        if mode == 'changed_client_timeout':
                            kwargs['active'].participant.motion_worker_config['timeout'] = 24
                        if mode == 'changed_client_socket':
                            kwargs['active'].participant.server_tcp = object()
                        return 1
                    def register_saved(self, index):
                        self.checked(); events.append(('register', index)); clock[0] += 10
                    def pull(self):
                        self.checked(); self.checked()
                        self.sequence += 1
                        events.append('pull')
                        clock[0] += 10
                        sample = {'version': 1, 'epoch': 'a'*32, 'generation': 'd'*32,
                                  'index': 1, 'sequence': self.sequence, 'sector_macro': 'test',
                                  'source_time': self.sequence, 'x': 0, 'y': 0, 'z': 0, 'velocity': None}
                        self.capture(sample)
                        if mode == 'long_delivery_failure':
                            raise RuntimeError('delivery result unconfirmed')
                        self.motion._tracks[('a'*32, 'd'*32, 1)] = {
                            'peer_samples': {('peer_1', 'f'*32): (self.sequence, motion_digest(sample))}}
                        return sample
                    def stop_remote(self):
                        self.checked(); events.append('source_stop'); self.state = 'remote_stopped'; return True
                    def close(self): events.append('source_close')
                source = Source()
                self_test = self
                def bind(_sock, motion, **options):
                    self.assertEqual(options['timeout'], 600 if long_mode else 300)
                    self.assertEqual(options.get('private_long_diagnostic', False), long_mode)
                    self.assertEqual(options['bind_timeout'], 120)
                    self.assertTrue(options['client_guard']())
                    self.assertTrue(options['saved_guard']('a'*32, 2))
                    clock[0] += 10
                    events.append('bind')
                    source.capture = options['validate_sample']
                    source.client_guard = options['client_guard']
                    source.saved_guard = options['saved_guard']
                    source.motion = motion
                    return source
                def stop_worker(*, source_stopped):
                    events.append('client_stop')
                    return source_stopped()
                kwargs['active'].participant.stop_motion_worker = Mock(side_effect=stop_worker)
                with patch.object(subject.time, 'monotonic', side_effect=lambda: clock[0]), \
                     patch.object(subject.time, 'sleep'), patch.object(subject, 'ExperimentalTCPJobDelivery', Delivery), \
                     patch.object(subject, 'ExperimentalTCPMotion', Motion), \
                     patch.object(subject, 'bind_running_source_motion', side_effect=bind), \
                     patch.object(subject.os, 'stat', return_value=SimpleNamespace(st_dev=1, st_ino=2)), \
                     patch.object(subject.os, 'fstat', return_value=SimpleNamespace(st_dev=3, st_ino=4)), \
                     patch.object(subject, 'check_process'), patch.object(subject, 'socket_owner', return_value=True):
                    if mode in ('complete', 'long_complete'):
                        result = subject.run(**kwargs)
                        self.assertTrue(result['client_motion_receipts_confirmed'])
                        self.assertGreaterEqual(kwargs['guard'].check.call_count, 8)
                        self.assertEqual(events, ['pump_active', 'bind', 'candidate', ('register', 1),
                                                  'pull', 'pull', 'source_stop', 'guard_stop',
                                                  'client_stop', 'source_close'])
                    else:
                        with self.assertRaises((ValueError, RuntimeError, TimeoutError)):
                            subject.run(**kwargs)
                        if mode == 'long_delivery_failure':
                            self.assertEqual(events.count('pull'), 1)
                            self.assertIn(('register', 1), events)
                        else:
                            self.assertNotIn(('register', 1), events)
                        self.assertNotIn('source_stop', events)

    @unittest.skipUnless(sys.platform=='linux','Linux process and socket ownership required')
    def test_invalid_pair_source_udp_is_rejected_before_tcp_dispatch(self):
        from tests import test_authority_experimental_tcp_motion as fixture
        for sequence, velocity in ((1, ('0','0','0')), (2, ('-','-','-'))):
            with self.subTest(sequence=sequence, velocity=velocity):
                case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp()
                sock=source=None;thread=None;errors=[]
                try:
                    conn=case.case.connect();case.case.offer_and_claim(conn);case.client(conn,1);case.case.host.tick(.1)
                    world=case.case.world;baseline=object();world._baseline=(7,baseline)
                    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
                    source=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);source.bind(('127.0.0.1',0))
                    source.connect(sock.getsockname());source.settimeout(4)
                    settings={'epoch':'b'*32,'baseline':100,'lease':'1'*32,'attempt':'2'*32,'generation':'c'*32,
                              'local_pair':{'nonce':'f'*32,'index':42,'delivery':True}}
                    def source_peer():
                        try:
                            prefix=['S',settings['lease'],settings['attempt']]
                            source.send('|'.join(prefix+['HELLO',settings['epoch'],settings['generation']]).encode())
                            packet=source.recv(769).decode().split('|');assert packet[3]=='BOUND'
                            source.send('|'.join(prefix+['ATTACHED',settings['epoch'],settings['generation']]).encode())
                            packet=source.recv(769).decode().split('|');assert packet[3]=='REGISTER_SAVED'
                            source.send('|'.join(prefix+['SAVED_REGISTERED',settings['epoch'],settings['generation'],
                                packet[6],packet[7],packet[8]]).encode())
                            packet=source.recv(769).decode().split('|');assert packet[3]=='PULL'
                            source.send('|'.join(prefix+['SAMPLE',settings['epoch'],settings['generation'],packet[6],
                                '42',str(sequence),'sector_a','1','1','2','3',*velocity]).encode())
                        except BaseException as error:errors.append(error)
                    thread=threading.Thread(target=source_peer);thread.start()
                    guard=SimpleNamespace(status=('ready',settings['epoch'],100,'d'*64),deadline=time.monotonic()+10,
                        check=Mock(return_value=True),stop=Mock(return_value=True))
                    active=SimpleNamespace(participant=SimpleNamespace(check_active=Mock(return_value=True)))
                    pump=recovered_client.WitnessGuardPump(SimpleNamespace(pump_loading=Mock()),time.monotonic()+10)
                    identity=(os.getpid(),linux_gate_live.start_ticks(os.getpid()))
                    with patch.object(subject.ExperimentalTCPMotion,'send',side_effect=AssertionError('TCP dispatch attempted')) as send:
                        with self.assertRaisesRegex(RuntimeError,'pair delivery lacks'):
                            subject.run(sock=sock,settings=settings,index=42,baseline=baseline,guard=guard,pump=pump,
                                active=active,host=case.case.host,world=world,identity=identity,verify=lambda:None,
                                verify_process=lambda:None,client_motion=True,verify_stopped=lambda:None)
                        send.assert_not_called()
                    self.assertEqual(case.received,[])
                    guard.stop.assert_not_called()
                finally:
                    if thread:thread.join(5)
                    if sock:sock.close()
                    if source:source.close()
                    cleanup_motion_fixture(case)
                self.assertFalse(thread.is_alive());self.assertEqual(errors,[])

    @unittest.skipUnless(sys.platform=='linux','Linux process and socket ownership required')
    def test_real_udp_tcp_delivery_with_retained_simulated_client(self):
        from tests import test_authority_experimental_tcp_motion as fixture
        case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity');case.setUp()
        sock=source=None;thread=None;errors=[]
        try:
            conn=case.case.connect();case.case.offer_and_claim(conn);case.client(conn,1);case.case.host.tick(.1)
            world=case.case.world;baseline=object();world._baseline=(7,baseline)
            self.assertIsNone(world.session.baseline_id)
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
            source=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);source.bind(('127.0.0.1',0))
            source.connect(sock.getsockname());source.settimeout(4)
            settings={'epoch':'b'*32,'baseline':100,'lease':'1'*32,'attempt':'2'*32,'generation':'c'*32}
            def source_peer():
                try:
                    source.send(f"S|{settings['lease']}|{settings['attempt']}|HELLO|{settings['epoch']}|{settings['generation']}".encode())
                    packet=source.recv(769).decode().split('|');assert packet[3]=='BOUND'
                    source.send(f"S|{settings['lease']}|{settings['attempt']}|ATTACHED|{settings['epoch']}|{settings['generation']}".encode())
                    for seq in range(4):
                        packet=source.recv(769).decode().split('|');request=packet[6]
                        prefix=['S',settings['lease'],settings['attempt']]
                        if packet[3]=='REGISTER_SAVED':reply=prefix+['SAVED_REGISTERED',settings['epoch'],settings['generation'],request,packet[7],packet[8]]
                        elif packet[3]=='PULL':reply=prefix+['SAMPLE',settings['epoch'],settings['generation'],request,'42',str(seq),'sector_a',str(seq),'1','2','3','-','-','-']
                        elif packet[3]=='STOP':reply=prefix+['STOPPED',settings['epoch'],settings['generation'],request]
                        else:raise ValueError('unexpected command')
                        source.send('|'.join(reply).encode())
                except BaseException as error:errors.append(error)
            thread=threading.Thread(target=source_peer);thread.start()
            guard=SimpleNamespace(status=('ready',settings['epoch'],100,'d'*64),deadline=time.monotonic()+10,
                check=Mock(return_value=True),stop=Mock(return_value=True))
            active=SimpleNamespace(participant=SimpleNamespace(check_active=Mock(return_value=True)))
            def stop_worker(*,source_stopped):
                self.assertTrue(source_stopped());self.assertTrue(source_stopped());return True
            active.participant.stop_motion_worker=Mock(side_effect=stop_worker)
            pump=recovered_client.WitnessGuardPump(SimpleNamespace(pump_loading=Mock()),time.monotonic()+10)
            identity=(os.getpid(),linux_gate_live.start_ticks(os.getpid()))
            result=subject.run(sock=sock,settings=settings,index=42,baseline=baseline,guard=guard,pump=pump,
                active=active,host=case.case.host,world=world,identity=identity,verify=lambda:None,verify_process=lambda:None,
                client_motion=True,verify_stopped=lambda:None)
            self.assertEqual(len(result['samples']),2);self.assertTrue(result['source_stopped_before_disconnect'])
            self.assertFalse(result['client_motion_proven']);self.assertGreater(guard.check.call_count,0)
            self.assertEqual(len(case.received),2);self.assertTrue(result['client_motion_receipts_confirmed'])
            self.assertEqual(result['client_receipt_sample_sha256'],[motion_digest(item[1]) for item in case.received])
            self.assertFalse(result['client_motion_visible_proven']);guard.stop.assert_called_once()
            active.participant.stop_motion_worker.assert_called_once()
        finally:
            if thread:thread.join(5)
            if sock:sock.close()
            if source:source.close()
            case.doCleanups()
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])

    def test_playback_invalid_fixture_is_rejected_before_any_operation(self):
        for options in (
                {'saved_playback_fixture': 'unknown'},
                {'saved_playback_fixture': 'recovery_enh_870'},
                {'playback_sample_observer': lambda _: True},
                {'playback_liveness_check': lambda: True},
                {'saved_playback_fixture': 'recovery_enh_870', 'playback_liveness_check': True},
                {'playback_begin': lambda: True}):
            events, kwargs, _ = self.context()
            kwargs.update(options)
            with self.subTest(options=tuple(options)), self.assertRaises(ValueError):
                subject.run(**kwargs)
            self.assertEqual(events, [])

    @unittest.skipUnless(sys.platform == 'linux', 'Linux process and socket ownership required')
    def test_real_twenty_six_samples_observed_after_receipt_then_ordered_drain(self):
        self.exercise_twenty_six_samples(use_identity_scope=True)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux process and socket ownership required')
    def test_real_playback_without_optional_identity_scope(self):
        self.exercise_twenty_six_samples(use_identity_scope=False)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux process and socket ownership required')
    def test_real_playback_with_separate_liveness_checks(self):
        self.exercise_twenty_six_samples(use_identity_scope=True, use_liveness_check=True)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux process and socket ownership required')
    def test_latest_real_udp_tcp_keeps_enrollment_and_final_receipt_with_slow_consumer(self):
        self.exercise_twenty_six_samples(use_identity_scope=True, use_liveness_check=True, latest=True)

    def exercise_twenty_six_samples(self, *, use_identity_scope, use_liveness_check=False, latest=False):
        """Real UDP/TCP and ownership guards, with a simulated source/client."""
        from tests import test_authority_experimental_tcp_motion as fixture
        from test_authority_paired_playback_evidence import source_sample
        case = fixture.MotionTCP('test_invalid_values_and_no_fake_velocity')
        case.setUp()
        events, errors = [], []
        sock = source = thread = None
        expected = [source_sample(n) for n in range(1, 27)]
        try:
            conn = case.case.connect(); case.case.offer_and_claim(conn)
            case.client(conn, 1, delay=.35 if latest else 0); case.case.host.tick(.1)
            world = case.case.world; baseline = object(); world._baseline = (7, baseline)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.bind(('127.0.0.1', 0))
            source = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); source.bind(('127.0.0.1', 0))
            source.connect(sock.getsockname()); source.settimeout(10)
            settings = dict(epoch=expected[0]['epoch'], baseline=10082, lease='1'*32,
                            attempt='2'*32, generation='c'*32)
            def source_peer():
                try:
                    prefix = ['S', settings['lease'], settings['attempt']]
                    identity = [settings['epoch'], settings['generation']]
                    source.send('|'.join(prefix+['HELLO']+identity).encode())
                    self.assertEqual(source.recv(769).decode().split('|')[3], 'BOUND')
                    source.send('|'.join(prefix+['ATTACHED']+identity).encode())
                    count = 0
                    while True:
                        packet = source.recv(769).decode().split('|'); request = packet[6]
                        if packet[3] == 'REGISTER_SAVED':
                            reply = prefix+['SAVED_REGISTERED']+identity+[request, packet[7], packet[8]]
                        elif packet[3] == 'PULL':
                            sample = expected[count]; count += 1
                            rate = ['-', '-', '-'] if sample['velocity'] is None else [str(sample['velocity'][a]) for a in ('x','y','z')]
                            reply = prefix+['SAMPLE']+identity+[request, '1318', str(count), sample['sector_macro'],
                                str(sample['source_time']), str(sample['x']), str(sample['y']), str(sample['z'])]+rate
                        elif packet[3] == 'STOP':
                            self.assertEqual(count, 26)
                            events.append(('source_stop', time.monotonic()))
                            source.send('|'.join(prefix+['STOPPED']+identity+[request]).encode())
                            break
                        else:
                            raise AssertionError('unexpected source command')
                        source.send('|'.join(reply).encode())
                except BaseException as error:
                    errors.append(error)
            thread = threading.Thread(target=source_peer); thread.start()
            guard = SimpleNamespace(status=('ready', settings['epoch'], 10082, 'd'*64),
                deadline=time.monotonic()+25, check=Mock(side_effect=AssertionError('ordinary checkpoint check used')),
                stop=Mock(side_effect=lambda: events.append(('guard_stop', time.monotonic())) or True))
            observed = []
            scope_depth = [0]
            scope_calls = []
            @contextmanager
            def identity_scope():
                scope_depth[0] += 1
                self.assertLessEqual(scope_depth[0], 2)
                scope_calls.append(('enter', scope_depth[0]))
                try:
                    yield
                finally:
                    scope_calls.append(('exit', scope_depth[0]))
                    scope_depth[0] -= 1
            def check_active(**_options):
                self.assertIn(scope_depth[0], (1, 2) if use_identity_scope else (0,))
                return True
            def observe(sample):
                self.assertEqual(scope_depth[0], 0)
                self.assertIsNone(case.case.host._control._reader_lease)
                self.assertFalse(case.case.host._busy)
                if latest:
                    self.assertEqual(case.received[len(observed)][1], sample)
                    self.assertTrue(case.case.host._control._motion_idle())
                    self.assertTrue(case.case.host._control._latest_motion.blocked)
                else:
                    self.assertEqual(case.received[-1][1], sample)
                    self.assertEqual(len(case.received), len(observed)+1)
                observed.append(sample)
                events.append(('observed', time.monotonic()))
                return True
            def stop_worker(*, source_stopped):
                self.assertTrue(source_stopped())
                events.append(('client_stop', time.monotonic()))
                return True
            active = SimpleNamespace(participant=SimpleNamespace(check_active=Mock(side_effect=check_active),
                stop_motion_worker=Mock(side_effect=stop_worker)))
            liveness_check = Mock(return_value=True)
            full_check = Mock()
            pump = recovered_client.WitnessGuardPump(SimpleNamespace(pump_loading=Mock()), time.monotonic()+25)
            latest_options = dict(latest_playback=True, playback_checkpoint_lifetime=lambda: True) if latest else {}
            result = subject.run(sock=sock, settings=settings, index=1318, baseline=baseline, guard=guard,
                pump=pump, active=active, host=case.case.host, world=world,
                identity=(os.getpid(), linux_gate_live.start_ticks(os.getpid())), verify=full_check,
                verify_process=lambda:None, client_motion=True, verify_stopped=lambda:None,
                saved_playback_fixture='recovery_enh_870', playback_sample_observer=observe,
                playback_identity_scope=identity_scope if use_identity_scope else None,
                playback_liveness_check=liveness_check if use_liveness_check else None,
                playback_begin=lambda: events.append(('begin', time.monotonic())) or True,
                playback_checkpoint_check=lambda: pump() or True,
                playback_checkpoint_stop=lambda: events.append(('checkpoint_stop_hook', time.monotonic())) or guard.stop(),
                **latest_options)
            if latest:
                sequences = [sample['sequence'] for sample in observed]
                self.assertEqual(sequences[0], 1)
                self.assertEqual(sequences[-1], 26)
                self.assertLess(len(sequences), 26)  # Slow ACKs coalesce unsent positions.
                self.assertEqual(observed, [expected[sequence-1] for sequence in sequences])
                self.assertEqual(result['latest_playback']['queued_sequences'], list(range(1, 27)))
                self.assertEqual(result['latest_playback']['acknowledged_sequences'], sequences)
                self.assertIs(result['latest_playback']['batch_latest_saved_checks'], True)
                self.assertIsNone(case.case.host._control._latest_source)
            else:
                self.assertEqual(observed, expected)
            self.assertGreater(full_check.call_count, 26)
            if use_liveness_check:
                self.assertGreater(liveness_check.call_count, 26)
                active.participant.check_active.assert_not_called()
            else:
                liveness_check.assert_not_called()
            if use_identity_scope:
                self.assertIn(('enter', 2), scope_calls)
            else:
                self.assertEqual(scope_calls, [])
            self.assertEqual(sum(event == 'enter' for event, _ in scope_calls),
                             sum(event == 'exit' for event, _ in scope_calls))
            self.assertEqual(scope_depth[0], 0)
            self.assertEqual([row[1] for row in case.received], observed)
            self.assertEqual(result['client_receipt_sample_sha256'], [motion_digest(s) for s in observed])
            times = dict(events)
            self.assertLess(events.index(('begin', times['begin'])), 1)
            self.assertGreaterEqual(times['guard_stop']-times['source_stop'], 1.25)
            self.assertLessEqual(times['checkpoint_stop_hook'], times['guard_stop'])
            self.assertLess(times['source_stop'], times['guard_stop'])
            self.assertLess(times['guard_stop'], times['client_stop'])
            self.assertEqual(result['saved_playback']['source_sample_count'], 26)
            self.assertFalse(result['client_motion_proven'])
            guard.check.assert_not_called()
        finally:
            if thread: thread.join(10)
            if sock: sock.close()
            if source: source.close()
            cleanup_motion_fixture(case)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_receipt_digest_and_client_stop_fences_fail_closed(self):
        for mode in ('ok','wrong_sample','wrong_digest','no_receipt','worker_failure','bad_socket',
                     'pair_zero','pair_nonzero','pair_no_sample','pair_unknown_rate','pair_wrong_index',
                     'pair_wrong_sequence','pair_wrong_digest','pair_worker_failure','pair_source_stop',
                     'pair_guard_stop','pair_bad_socket','pair_sector_ok','pair_sector_peer_change',
                     'pair_sector_poll_failure','pair_sector_bad_stop','pair_sector_bad_receipt'):
            with self.subTest(mode=mode):
                events,kwargs,_=self.context();kwargs['client_motion']=True;kwargs['verify_stopped']=Mock()
                pair_delivery = mode.startswith('pair_')
                if pair_delivery:
                    kwargs['settings']['local_pair']={'nonce':'e'*32,'index':1,'delivery':True}
                if mode=='pair_guard_stop':
                    kwargs['guard'].stop=Mock(side_effect=lambda: events.append('guard_stop') or False)
                diagnostics = subject.SourceProbeDiagnostics()
                kwargs['diagnostics'] = diagnostics
                kwargs['world'].session.players=kwargs['world'].session.ready_players=((1,'one'),)
                selected={'id':'peer_1','incarnation':'f'*32}
                if mode.startswith('pair_sector_'):
                    kwargs['active'].participant.handle=1
                    kwargs['active'].participant._sector_incarnation='f'*32
                    def poll_sector(recipient, receipt):
                        events.append('sector_poll')
                        self.assertEqual(recipient,selected)
                        self.assertEqual(receipt[0],2)
                        if mode=='pair_sector_peer_change':selected['incarnation']='9'*32
                        if mode=='pair_sector_poll_failure':raise RuntimeError('sector log invalid')
                        return 'sector_a'
                    def stop_sector():
                        events.append('sector_stop')
                        return mode!='pair_sector_bad_stop'
                    kwargs['sector_poll']=poll_sector;kwargs['sector_stop']=stop_sector
                    kwargs['sector_arm']=lambda: events.append('sector_arm') or True
                    kwargs['sector_incarnation']='f'*32
                class Delivery:
                    def __init__(self,*a,**kw):pass
                    def bind_test_incarnation(self,handle,incarnation,*,enabled):
                        assert (handle,incarnation,enabled)==(1,'f'*32,True)
                        events.append('bind_incarnation')
                        return True
                    def membership(self):return (selected,)
                class Motion:
                    def __init__(self,*a,**kw):self._tracks={}
                class Sock:
                    def getsockname(self):return ('127.0.0.1',1)
                    def getpeername(self):return ('127.0.0.1',2)
                    def fileno(self):return 99
                kwargs['sock']=Sock()
                class Source:
                    state='ready';seq=0
                    def register_saved(self,index):events.append('register')
                    def pull(self):
                        events.append('pull')
                        self.seq+=1
                        if mode=='pair_no_sample':return None
                        sample={'version':1,'epoch':'a'*32,'generation':'d'*32,'index':1,'sequence':self.seq,
                            'sector_macro':'test','source_time':self.seq,'x':0,'y':0,'z':0,'velocity':None}
                        if pair_delivery and mode!='pair_unknown_rate':
                            sample['velocity']={'x':1 if mode=='pair_nonzero' else 0,'y':0,'z':0}
                        if pair_delivery:sample['sequence']=2
                        if mode=='pair_wrong_index':sample['index']=2
                        if mode=='pair_wrong_sequence':sample['sequence']=1
                        self.capture(sample)
                        events.append('tcp_send')
                        digest='0'*64 if mode in ('wrong_digest','pair_wrong_digest','pair_sector_bad_receipt') else motion_digest(sample)
                        self.motion._tracks[('a'*32,'d'*32,1)]={'peer_samples':{('peer_1','f'*32):(sample['sequence'],digest)}}
                        if mode=='no_receipt':return None
                        if mode=='wrong_sample':return dict(sample,x=1)
                        return sample
                    def stop_remote(self):
                        events.append('source_stop');self.state='remote_stopped'
                        return mode!='pair_source_stop'
                    def close(self):events.append('source_close')
                source=Source()
                def bind(sock,motion,**kw):
                    self.assertEqual(kw['select_recipients']({},(selected,)),[selected])
                    source.capture=kw['validate_sample'];source.motion=motion;return source
                def stop_worker(*,source_stopped):
                    events.append('client_stop')
                    kwargs['active'].participant.check_active.side_effect=AssertionError('reentrant active guard')
                    if mode in ('worker_failure','pair_worker_failure'):return False
                    if not source_stopped():raise RuntimeError('source fence')
                    return True
                kwargs['active'].participant.stop_motion_worker=Mock(side_effect=stop_worker)
                with patch.object(subject,'ExperimentalTCPJobDelivery',Delivery),patch.object(subject,'ExperimentalTCPMotion',Motion), \
                     patch.object(subject,'bind_running_source_motion',side_effect=bind), \
                     patch.object(subject.os,'stat',return_value=SimpleNamespace(st_dev=1,st_ino=2)), \
                     patch.object(subject.os,'fstat',return_value=SimpleNamespace(st_dev=3,st_ino=4)), \
                     patch.object(subject,'check_process'),patch.object(subject,'socket_owner',return_value=mode not in ('bad_socket','pair_bad_socket')), \
                     patch.object(subject.time,'sleep'):
                    if mode in ('ok','pair_zero','pair_nonzero','pair_sector_ok'):
                        result=subject.run(**kwargs)
                        self.assertTrue(result['client_motion_receipts_confirmed'])
                        self.assertEqual(diagnostics.snapshot()['confirmed_client_receipts'], 1 if pair_delivery else 2)
                        self.assertEqual(len(result['client_receipt_sample_sha256']),1 if pair_delivery else 2)
                        if pair_delivery:
                            self.assertTrue(result['pair_delivery'])
                            self.assertTrue(result['pair_sample_velocity_present'])
                            self.assertEqual(result['samples'][0]['sequence'],2)
                            self.assertNotIn('second_sample_velocity_present',result)
                            self.assertEqual(events.count('pull'),1)
                            self.assertLess(events.index('source_stop'),events.index('guard_stop'))
                            self.assertLess(events.index('guard_stop'),events.index('client_stop'))
                            if mode=='pair_sector_ok':
                                self.assertLess(events.index('bind_incarnation'),events.index('pull'))
                                self.assertLess(events.index('sector_arm'),events.index('tcp_send'))
                                self.assertLess(events.index('tcp_send'),events.index('sector_poll'))
                                self.assertLess(events.index('sector_poll'),events.index('source_stop'))
                                self.assertLess(events.index('client_stop'),events.index('sector_stop'))
                                self.assertLess(events.index('sector_stop'),events.index('source_close'))
                        else:
                            self.assertFalse(result['second_sample_velocity_present'])
                        self.assertLess(events.index('source_stop'),events.index('client_stop'))
                        self.assertLess(events.index('client_stop'),events.index('source_close'))
                    else:
                        with self.assertRaises(RuntimeError):subject.run(**kwargs)
                        self.assertNotIn('source_close',events)
                        if pair_delivery:self.assertEqual(events.count('pull'),1)
                        if mode in ('pair_unknown_rate','pair_wrong_index','pair_wrong_sequence'):
                            self.assertNotIn('tcp_send',events)
                        if mode=='pair_wrong_digest':self.assertIn('tcp_send',events)
                        if mode=='pair_sector_bad_receipt':self.assertNotIn('sector_poll',events)
                        if mode in ('pair_sector_peer_change','pair_sector_poll_failure'):
                            self.assertNotIn('client_stop',events)
                        if mode in ('wrong_sample', 'wrong_digest', 'no_receipt'):
                            self.assertEqual(diagnostics.snapshot()['prevalidated_samples'], 1)
                            self.assertEqual(diagnostics.snapshot()['confirmed_client_receipts'], 0)
