"""Source probe lifecycle and explicit evidence scope; no X4 or sockets."""
from pathlib import Path
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

class Probe(unittest.TestCase):
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
                     'changed_client_timeout', 'changed_client_socket', 'wrong_sent_timeout'):
            with self.subTest(mode=mode):
                events, kwargs, _ = self.context()
                clock = [1.0]
                kwargs['guard'].deadline = 1000
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
                if mode == 'bad_order':
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
                    def __init__(self, _host, *, enabled, timeout):
                        self_test.assertTrue(enabled)
                        self_test.assertEqual(timeout, 240)
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
                        if mode == 'deadline': clock[0] = 601
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
                        self.motion._tracks[('a'*32, 'd'*32, 1)] = {
                            'peer_samples': {('peer_1', 'f'*32): (self.sequence, motion_digest(sample))}}
                        return sample
                    def stop_remote(self):
                        self.checked(); events.append('source_stop'); self.state = 'remote_stopped'; return True
                    def close(self): events.append('source_close')
                source = Source()
                self_test = self
                def bind(_sock, motion, **options):
                    self.assertEqual(options['timeout'], 300)
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
                    if mode == 'complete':
                        result = subject.run(**kwargs)
                        self.assertTrue(result['client_motion_receipts_confirmed'])
                        self.assertGreaterEqual(kwargs['guard'].check.call_count, 8)
                        self.assertEqual(events, ['pump_active', 'bind', 'candidate', ('register', 1),
                                                  'pull', 'pull', 'source_stop', 'guard_stop',
                                                  'client_stop', 'source_close'])
                    else:
                        with self.assertRaises((ValueError, RuntimeError, TimeoutError)):
                            subject.run(**kwargs)
                        self.assertNotIn(('register', 1), events)
                        self.assertNotIn('source_stop', events)

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

    def test_receipt_digest_and_client_stop_fences_fail_closed(self):
        for mode in ('ok','wrong_sample','wrong_digest','no_receipt','worker_failure','bad_socket'):
            with self.subTest(mode=mode):
                events,kwargs,_=self.context();kwargs['client_motion']=True;kwargs['verify_stopped']=Mock()
                diagnostics = subject.SourceProbeDiagnostics()
                kwargs['diagnostics'] = diagnostics
                kwargs['world'].session.players=kwargs['world'].session.ready_players=((1,'one'),)
                selected={'id':'peer_1','incarnation':'f'*32}
                class Delivery:
                    def __init__(self,*a,**kw):pass
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
                        self.seq+=1
                        sample={'version':1,'epoch':'a'*32,'generation':'d'*32,'index':1,'sequence':self.seq,
                            'sector_macro':'test','source_time':self.seq,'x':0,'y':0,'z':0,'velocity':None}
                        self.capture(sample)
                        digest='0'*64 if mode=='wrong_digest' else motion_digest(sample)
                        self.motion._tracks[('a'*32,'d'*32,1)]={'peer_samples':{('peer_1','f'*32):(self.seq,digest)}}
                        if mode=='no_receipt':return None
                        if mode=='wrong_sample':return dict(sample,x=1)
                        return sample
                    def stop_remote(self):events.append('source_stop');self.state='remote_stopped';return True
                    def close(self):events.append('source_close')
                source=Source()
                def bind(sock,motion,**kw):
                    self.assertEqual(kw['select_recipients']({},(selected,)),[selected])
                    source.capture=kw['validate_sample'];source.motion=motion;return source
                def stop_worker(*,source_stopped):
                    events.append('client_stop')
                    kwargs['active'].participant.check_active.side_effect=AssertionError('reentrant active guard')
                    if mode=='worker_failure':return False
                    if not source_stopped():raise RuntimeError('source fence')
                    return True
                kwargs['active'].participant.stop_motion_worker=Mock(side_effect=stop_worker)
                with patch.object(subject,'ExperimentalTCPJobDelivery',Delivery),patch.object(subject,'ExperimentalTCPMotion',Motion), \
                     patch.object(subject,'bind_running_source_motion',side_effect=bind), \
                     patch.object(subject.os,'stat',return_value=SimpleNamespace(st_dev=1,st_ino=2)), \
                     patch.object(subject.os,'fstat',return_value=SimpleNamespace(st_dev=3,st_ino=4)), \
                     patch.object(subject,'check_process'),patch.object(subject,'socket_owner',return_value=mode!='bad_socket'), \
                     patch.object(subject.time,'sleep'):
                    if mode=='ok':
                        result=subject.run(**kwargs)
                        self.assertTrue(result['client_motion_receipts_confirmed'])
                        self.assertEqual(diagnostics.snapshot()['confirmed_client_receipts'], 2)
                        self.assertEqual(len(result['client_receipt_sample_sha256']),2)
                        self.assertFalse(result['second_sample_velocity_present'])
                        self.assertLess(events.index('source_stop'),events.index('client_stop'))
                        self.assertLess(events.index('client_stop'),events.index('source_close'))
                    else:
                        with self.assertRaises(RuntimeError):subject.run(**kwargs)
                        self.assertNotIn('source_close',events)
                        if mode in ('wrong_sample', 'wrong_digest', 'no_receipt'):
                            self.assertEqual(diagnostics.snapshot()['prevalidated_samples'], 1)
                            self.assertEqual(diagnostics.snapshot()['confirmed_client_receipts'], 0)
