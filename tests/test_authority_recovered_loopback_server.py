"""Supervisor socket-loop coverage only; no native X4 is launched here."""
import importlib.util
import gzip
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
import shutil
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('authority_recovered_loopback_server',
    ROOT/'tools/dev/authority_recovered_loopback_server.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
from authority.checkpoints import CheckpointStore
import authority.checkpoints as checkpoints
from authority.experimental_local_host import ExperimentalLocalHost
from authority.experimental_tcp_control import ExperimentalTCPControl, offer_request
from authority.recovery import stage_confirmed_recovery
from authority.save_transfer import SaveOffers
from authority.trusted_load_messages import decode_bound_offer, encode_load_claim
from authority.trusted_marker_load_session import TrustedMarkerLoadSession
from authority.world import WorldCoordinator
from lockstep.launcher.joinfiles import FileService
from test_authority_experimental_local_host import Engine, Participants
from test_authority_trusted_marker_load_session import XML, MARKER, claim_for



class WitnessJoinModeTests(unittest.TestCase):
    def test_pair_delivery_requires_both_existing_opt_ins(self):
        self.assertFalse(MODULE.diagnostic_local_pair_delivery(SimpleNamespace(), False, False))
        args = SimpleNamespace(diagnostic_local_pair_delivery=True)
        self.assertTrue(MODULE.diagnostic_local_pair_delivery(args, True, True))
        for pair, motion in ((False, True), (True, False), (False, False)):
            with self.subTest(pair=pair, motion=motion), self.assertRaises(ValueError):
                MODULE.diagnostic_local_pair_delivery(args, pair, motion)
        with self.assertRaises(ValueError):
            MODULE.diagnostic_local_pair_delivery(SimpleNamespace(diagnostic_local_pair_delivery=1), True, True)

    def test_local_pair_requires_explicit_single_index(self):
        self.assertFalse(MODULE.diagnostic_local_pair(SimpleNamespace(), False, None, None))
        args = SimpleNamespace(diagnostic_local_pair=True)
        self.assertTrue(MODULE.diagnostic_local_pair(args, True, 1, None))
        for join, index, candidates in ((False, 1, None), (True, None, None),
                                        (True, True, None), (True, 1, (1,))):
            with self.subTest(join=join, index=index, candidates=candidates):
                with self.assertRaises(ValueError):
                    MODULE.diagnostic_local_pair(args, join, index, candidates)
        with self.assertRaises(ValueError):
            MODULE.diagnostic_local_pair(SimpleNamespace(diagnostic_local_pair=1), True, 1, None)

    def test_pair_nonce_redaction_rejects_ambiguity(self):
        token = 'c' * 32
        config = 'authority_control_lease="' + 'a' * 32 + '",authority_motion_pair_nonce="' + token + '"'
        self.assertNotIn(token, MODULE.redact_recovery_config(config))
        with self.assertRaises(ValueError):
            MODULE.redact_recovery_config(config + ',authority_motion_pair_nonce="' + token + '"')
        with self.assertRaises(ValueError):
            MODULE.redact_recovery_config(config.replace(token, 'bad'))

    def test_pair_evidence_requires_stopped_process_and_preserves_prior_error(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            log = profile / 'engine-output.log'
            log.write_text('[X4LAN] AUTH_LOCAL_PAIR estimated dt=0.1 vx=1 vy=2 vz=3\n')
            result = {'success': True}
            MODULE.record_local_pair_result(result, profile, 7, [])
            self.assertTrue(result['success'])
            self.assertEqual(result['local_pair_diagnostic']['vx'], 1)
            self.assertFalse(result['local_pair_diagnostic']['native_velocity_proven'])
            result = {'success': True}
            MODULE.record_local_pair_result(result, profile, 7, [123])
            self.assertFalse(result['success'])
            self.assertEqual(result['local_pair_diagnostic']['status'], 'not_verified_cleanup')
            log.write_text('[X4LAN] AUTH_LOCAL_PAIR invalid\n')
            result = {'success': True}
            MODULE.record_local_pair_result(result, profile, 7, [])
            self.assertFalse(result['success'])
            self.assertEqual(result['local_pair_diagnostic']['status'], 'invalid')
            result = {'success': False, 'error': 'prior failure'}
            MODULE.record_local_pair_result(result, profile, 7, [])
            self.assertEqual(result['error'], 'prior failure')
            self.assertEqual(result['local_pair_diagnostic']['status'], 'invalid')

    def test_pair_log_failure_is_checked_after_existing_final_fences(self):
        # Pin the supervisor's order; the preceding test exercises failure semantics.
        source = inspect.getsource(MODULE.run)
        final_checks = source.index('verify_final_recovery(watch)')
        protected = source.index("raise ValueError('final protected recovery inputs changed')", final_checks)
        pair = source.index('record_local_pair_result(result, profile, source_index, remaining)', protected)
        lock = source.index('finish_recovery_lock(lockbox, remaining, services_stopped, errors)', pair)
        self.assertLess(final_checks, protected)
        self.assertLess(protected, pair)
        self.assertLess(pair, lock)

    def test_redaction_requires_confirmed_process_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'config.lua';original='authority_control_lease="'+('a'*32)+'"'
            for remaining in (None,[123]):
                path.write_text(original)
                with self.assertRaises(RuntimeError):MODULE.redact_stopped_server_config(path,remaining)
                self.assertEqual(path.read_text(),original)
            MODULE.redact_stopped_server_config(path,[])
            self.assertEqual(path.read_text(),'authority_control_lease="redacted"')

    def test_source_tokens_are_redacted_and_ambiguous_tokens_refused(self):
        keys=('lease','attempt','generation','nonce','saved_nonce')
        config='authority_control_lease="'+('a'*32)+'",'+','.join(
            'authority_motion_'+key+'="'+('b'*32)+'"' for key in keys)
        redacted=MODULE.redact_recovery_config(config)
        self.assertNotIn('a'*32,redacted);self.assertNotIn('b'*32,redacted)
        self.assertEqual(redacted.count('"redacted"'),6)
        with self.assertRaises(ValueError):MODULE.redact_recovery_config(config+',authority_motion_nonce="'+('b'*32)+'"')
        with self.assertRaises(ValueError):MODULE.redact_recovery_config(config.replace('authority_motion_attempt="'+('b'*32)+'"','authority_motion_attempt="bad"'))

    def test_source_index_requires_explicit_witness_join_and_range(self):
        self.assertIsNone(MODULE.diagnostic_source_index(SimpleNamespace(),False))
        self.assertEqual(MODULE.diagnostic_source_index(SimpleNamespace(diagnostic_source_index=1),True),1)
        for index,join in ((True,True),(0,True),(200001,True),(1,False)):
            with self.subTest(index=index,join=join),self.assertRaises(ValueError):
                MODULE.diagnostic_source_index(SimpleNamespace(diagnostic_source_index=index),join)

    def test_source_candidates_are_bounded_explicit_and_exclusive(self):
        self.assertIsNone(MODULE.diagnostic_source_candidates(SimpleNamespace(),False,None))
        self.assertEqual(MODULE.diagnostic_source_candidates(SimpleNamespace(diagnostic_source_candidates=[1,2]),True,None),(1,2))
        for values,join,index in (([],True,None),([1,1],True,None),([True],True,None),([200001],True,None),([1],False,None),([1],True,1), (list(range(1,34)),True,None)):
            with self.subTest(values=values),self.assertRaises(ValueError):
                MODULE.diagnostic_source_candidates(SimpleNamespace(diagnostic_source_candidates=values),join,index)

    def test_source_stop_precedes_client_finish_and_failure_keeps_client_owned(self):
        for mode in ('ok','missing_receipt','exception'):
            events=[];active=SimpleNamespace(finish=lambda:events.append('finish') or {'done':True})
            clients=[];context=[('guard','baseline','pump')]
            def verify():
                self.assertEqual(clients,[active]);events.append('verify')
            def probe(*args):
                self.assertEqual(args,(*context[0],active));events.append('probe')
                if mode=='exception':raise RuntimeError('lost STOP')
                return {'source_stopped_before_disconnect':mode=='ok'}
            if mode=='ok':
                _,result=MODULE.finish_source_diagnostic(active,clients,context,verify=verify,probe=probe)
                self.assertEqual(result,{'done':True});self.assertEqual(events,['verify','probe','verify','finish'])
                self.assertEqual(clients,[])
            else:
                with self.assertRaises(RuntimeError):
                    MODULE.finish_source_diagnostic(active,clients,context,verify=verify,probe=probe)
                self.assertNotIn('finish',events);self.assertEqual(clients,[active])

    def test_post_stop_guard_replaces_live_guard_only_after_probe(self):
        events=[];active=SimpleNamespace(finish=lambda:events.append('finish') or True);clients=[]
        def verify():events.append('active')
        def verify_after():events.append('stopped')
        def probe(*_):events.append('source_and_client_stop');return {'source_stopped_before_disconnect':True}
        MODULE.finish_source_diagnostic(active,clients,[('guard','baseline','pump')],
            verify=verify,verify_after=verify_after,probe=probe)
        self.assertEqual(events,['active','source_and_client_stop','stopped','finish'])

    def test_client_motion_requires_explicit_source(self):
        self.assertFalse(MODULE.diagnostic_client_motion(SimpleNamespace(),False))
        self.assertTrue(MODULE.diagnostic_client_motion(SimpleNamespace(diagnostic_client_motion=True),True))
        for value,enabled in ((True,False),(1,True)):
            with self.assertRaises(ValueError):MODULE.diagnostic_client_motion(SimpleNamespace(diagnostic_client_motion=value),enabled)

    def test_client_finish_refuses_missing_receipts_or_worker_stop(self):
        valid={'source_stopped_before_disconnect':True,'client_motion_receipts_confirmed':True,
               'client_worker_stop_confirmed':True,'client_receipt_sample_sha256':['a'*64,'b'*64]}
        for change in ({'client_motion_receipts_confirmed':False},{'client_worker_stop_confirmed':False},
                       {'client_receipt_sample_sha256':['a'*64]},{'client_receipt_sample_sha256':['a'*64,'bad']}):
            active=SimpleNamespace(finish=Mock());clients=[];observation=dict(valid,**change)
            with self.subTest(change=change),self.assertRaises(RuntimeError):
                MODULE.finish_source_diagnostic(active,clients,[('guard','baseline','pump')],verify=lambda:None,
                    probe=lambda *_:observation,verify_after=lambda:None,require_client_receipts=True)
            active.finish.assert_not_called();self.assertEqual(clients,[active])

    def test_pair_finish_requires_exactly_one_confirmed_receipt_and_stops(self):
        valid={'source_stopped_before_disconnect':True,'client_motion_receipts_confirmed':True,
               'client_worker_stop_confirmed':True,'client_receipt_sample_sha256':['a'*64],
               'pair_delivery':True,'pair_sample_velocity_present':True}
        for change in ({}, {'client_receipt_sample_sha256':[]},
                       {'client_receipt_sample_sha256':['a'*64,'b'*64]},
                       {'client_receipt_sample_sha256':['bad']}, {'pair_delivery':False},
                       {'pair_sample_velocity_present':False}, {'client_worker_stop_confirmed':False}):
            events=[];active=SimpleNamespace(finish=lambda:events.append('finish') or True);clients=[]
            observation=dict(valid,**change)
            with self.subTest(change=change):
                if not change:
                    MODULE.finish_source_diagnostic(active,clients,[('guard','baseline','pump')],
                        verify=lambda:events.append('verify'),probe=lambda *_:observation,
                        verify_after=lambda:events.append('stopped'),require_client_receipts=True,pair_delivery=True)
                    self.assertEqual(events,['verify','stopped','finish'])
                    self.assertEqual(clients,[])
                else:
                    with self.assertRaises(RuntimeError):
                        MODULE.finish_source_diagnostic(active,clients,[('guard','baseline','pump')],
                            verify=lambda:events.append('verify'),probe=lambda *_:observation,
                            verify_after=lambda:events.append('stopped'),require_client_receipts=True,pair_delivery=True)
                    self.assertEqual(events,['verify']);self.assertEqual(clients,[active])

    def test_join_requires_explicit_single_client_and_preserves_other_modes(self):
        self.assertEqual(MODULE.witness_mode(SimpleNamespace()), (False, None))
        self.assertEqual(MODULE.witness_mode(SimpleNamespace(registry_witness='verify')), (False, 'verify'))
        self.assertEqual(MODULE.witness_mode(SimpleNamespace(registry_witness_join=True, diagnostic_client=True)), (True, 'verify'))
        for options in (
            {'registry_witness_join': True},
            {'registry_witness_join': True, 'diagnostic_client': True, 'registry_witness': 'verify'},
            {'registry_witness_join': True, 'diagnostic_client': True, 'registry_enroll': True},
            {'registry_witness_join': True, 'diagnostic_client': True, 'diagnostic_overlap': True},
            {'registry_witness_join': True, 'diagnostic_client': True, 'diagnostic_clients': 2},
            {'registry_witness_join': 1, 'diagnostic_client': True},
            {'registry_witness': 'verify', 'diagnostic_client': True},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                MODULE.witness_mode(SimpleNamespace(**options))

class Control:
    def __init__(self): self._peers = {}


class Host:
    def __init__(self): self._control=Control(); self.handles=0
    def adopt(self, conn):
        self.handles += 1
        conn.setblocking(False)
        self._control._peers[conn]={'stage':'attached', 'handle':self.handles}
    def tick(self, timeout):
        for conn, peer in tuple(self._control._peers.items()):
            try: data=conn.recv(1)
            except BlockingIOError: continue
            if not data:
                del self._control._peers[conn]; conn.close()
            elif data == b'A': peer['stage']='admitted'
            else: raise ValueError('unexpected fake command')
        time.sleep(min(timeout, .005))


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1',0)); self.listener.listen(4)
        self.host=Host(); self.stop=threading.Event(); self.result=[]; self.errors=[]
        def worker():
            try:
                self.result.append(MODULE.serve(self.listener,self.host,deadline=time.monotonic()+2,
                    check=lambda: None,should_stop=self.stop.is_set,tick_interval=.01))
            except BaseException as error: self.errors.append(error)
        self.thread=threading.Thread(target=worker); self.thread.start()
    def tearDown(self):
        self.stop.set(); self.thread.join(3); self.listener.close()
        for conn in tuple(self.host._control._peers): conn.close()
    def wait_for(self, predicate):
        deadline=time.monotonic()+1
        while not predicate():
            if time.monotonic()>=deadline: self.fail('condition timed out')
            time.sleep(.005)
    def test_empty_server_remains_available_after_disconnect(self):
        for expected in (1,2):
            client=socket.create_connection(self.listener.getsockname(),timeout=1)
            client.sendall(b'A')
            self.wait_for(lambda: self.host.handles == expected and
                any(p['stage']=='admitted' for p in self.host._control._peers.values()))
            client.close()
            self.wait_for(lambda: not self.host._control._peers)
            self.assertTrue(self.thread.is_alive())
        self.stop.set(); self.thread.join(2)
        self.assertFalse(self.errors)
        self.assertEqual(self.result,[{'accepted_connections':2,'admitted_connections':2}])
    def test_check_failure_propagates(self):
        self.stop.set(); self.thread.join(2)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1',0)); listener.listen(1)
            def failed(): raise RuntimeError('owned X4 disappeared')
            with self.assertRaisesRegex(RuntimeError,'owned X4 disappeared'):
                MODULE.serve(listener,Host(),deadline=time.monotonic()+1,check=failed)


class OwnedCleanupTests(unittest.TestCase):
    def test_recovery_lock_is_retained_when_service_drain_is_unconfirmed(self):
        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder) / 'lock'
            lock.touch()
            descriptor = os.open(lock, os.O_RDONLY)
            errors = []
            with patch.object(MODULE.live, 'release_lock_target') as release:
                MODULE.finish_recovery_lock([(descriptor, object())], [], False, errors)
            release.assert_not_called()
            self.assertTrue(lock.exists())
            self.assertTrue(any('lock retained' in error for error in errors))
            with self.assertRaises(OSError): os.fstat(descriptor)

    def test_missing_start_identity_is_unknown_even_after_launcher_exit(self):
        proc = Mock(); proc.poll.return_value = 0
        errors = []
        self.assertIsNone(MODULE.stop_owned_processes([[proc, None]], True, errors))
        self.assertIn('launcher identity unavailable', errors)

    def test_failed_stop_is_unknown_and_does_not_skip_other_processes(self):
        first, second = Mock(), Mock()
        errors = []
        def stop(proc, started):
            if proc is second: raise RuntimeError('stop unconfirmed')
            return []
        with patch.object(MODULE.snapshot, 'stop_owned', side_effect=stop) as stop_owned:
            self.assertIsNone(MODULE.stop_owned_processes([[first, 1], [second, 2]], True, errors))
        self.assertEqual(stop_owned.call_count, 2)
        self.assertIn('owned cleanup: RuntimeError', errors)

    def test_uncertain_helper_never_claims_empty_process_set(self):
        with patch.object(MODULE.snapshot, 'stop_owned') as stop_owned:
            self.assertIsNone(MODULE.stop_owned_processes([[Mock(), 1]], False, []))
        stop_owned.assert_not_called()


class PreviousSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.origin=self.root/'prior'; self.origin.mkdir()
        (self.origin/'checkpoints').mkdir()
        self.store=CheckpointStore(self.origin/'checkpoints')
        save=self.root/'save.gz'; save.write_bytes(gzip.compress(XML.encode()))
        self.checkpoint=self.store.publish(save,marker=MARKER); self.store.confirm(self.checkpoint)
        md=self.origin/'case/extensions/x4_lan_lab/md'; md.mkdir(parents=True)
        shutil.copyfile(ROOT/'src/authority/md/checkpoint_marker.xml',md/'authority_checkpoint_marker.xml')
        shutil.copyfile(ROOT/'tools/dev/authority_identity_fixture.xml',md/'authority_identity_fixture.xml')
        content=self.origin/'case/home/.config/EgoSoft/X4/45841/content.xml'
        content.parent.mkdir(parents=True); content.write_bytes(b'compatible content')
        self.profile=self.root/'profile'; self.profile.mkdir(); (self.profile/'content.xml').write_bytes(content.read_bytes())
        self.result={'supervisor_version':1, 'success':True, 'final_world_state':'paused',
                     'owned_processes_remaining':[], 'final_checkpoint_id':self.checkpoint.checkpoint_id,
                     'final_checkpoint_sha256':self.checkpoint.sha256}
        self.write_result()
    def write_result(self):
        (self.origin/'result.json').write_text(json.dumps(self.result))
    def test_own_confirmed_checkpoint_is_staged_and_compatible(self):
        stage=self.root/'stage'; stage.mkdir(mode=0o700)
        checkpoint,path=stage_confirmed_recovery(self.store,stage)
        self.assertEqual(checkpoint,self.checkpoint)
        self.assertEqual(path.read_bytes(),self.checkpoint.path.read_bytes())
        self.assertEqual(MODULE.verify_previous_source(self.store,checkpoint,self.profile),
                         (ROOT/'tools/dev/authority_identity_fixture.xml').read_bytes())
    def test_unclean_result_and_incompatible_content_are_refused(self):
        self.result['owned_processes_remaining']=[123]; self.write_result()
        with self.assertRaises(ValueError): MODULE.verify_previous_source(self.store,self.checkpoint,self.profile)
        self.result['owned_processes_remaining']=[]; self.write_result()
        (self.profile/'content.xml').write_bytes(b'different content')
        with self.assertRaises(ValueError): MODULE.verify_previous_source(self.store,self.checkpoint,self.profile)
    def test_witness_source_requires_clean_create_and_exact_scripts(self):
        md=self.origin/'case/extensions/x4_lan_lab/md'
        for name in ('authority_ship_registry.xml', 'authority_registry_witness.xml'):
            shutil.copyfile(ROOT/'tools/dev'/name, md/name)
        self.result['witness_diagnostic']={'phase':'create'}; self.write_result()
        self.assertTrue(MODULE.verify_previous_source(self.store, self.checkpoint, self.profile,
                                                      registry_status=True, witness_source=True))
        # Normal recovery never silently accepts the extra witness script.
        with self.assertRaises(ValueError):
            MODULE.verify_previous_source(self.store, self.checkpoint, self.profile, registry_status=True)
        self.result['success']=False; self.write_result()
        with self.assertRaises(ValueError):
            MODULE.verify_previous_source(self.store, self.checkpoint, self.profile,
                                          registry_status=True, witness_source=True)
        self.result['success']=True
        self.result.pop('witness_diagnostic'); self.result['witness_join']={'server_witness_verified':True}
        self.write_result()
        with self.assertRaises(ValueError):
            MODULE.verify_previous_source(self.store, self.checkpoint, self.profile,
                                          registry_status=True, witness_source=True)
        self.result['witness_diagnostic']={'phase':'verify'}; self.write_result()
        with self.assertRaises(ValueError):
            MODULE.verify_previous_source(self.store, self.checkpoint, self.profile,
                                          registry_status=True, witness_source=True)
        self.result['witness_diagnostic']['phase']='create'; self.write_result()
        (md/'authority_registry_witness.xml').write_text('modified')
        with self.assertRaises(ValueError):
            MODULE.verify_previous_source(self.store, self.checkpoint, self.profile,
                                          registry_status=True, witness_source=True)

    def test_unconfirmed_new_generation_is_refused(self):
        save=self.root/'different.gz'; save.write_bytes(gzip.compress(XML.encode()))
        self.store.publish(save,marker=MARKER)
        with self.assertRaises(ValueError): MODULE.verify_previous_source(self.store,self.checkpoint,self.profile)
    def test_failed_confirm_after_pointer_replace_cannot_be_recovery_source(self):
        save=self.root/'candidate.gz';save.write_bytes(gzip.compress(XML.encode()))
        candidate=self.store.publish(save,marker=MARKER)
        with patch.object(checkpoints,'_sync_dir',side_effect=OSError('simulated sync failure')):
            with self.assertRaises(OSError):
                MODULE.confirm_witness_after_cleanup(self.store,candidate,{'success':True},[],[])
        # Replacement occurred before the simulated failure, so the pointer
        # alone must never authorize this source.
        self.assertEqual(self.store.latest_marked_confirmed(),candidate)
        self.result.update(final_checkpoint_id=candidate.checkpoint_id,final_checkpoint_sha256=candidate.sha256)
        self.write_result()
        self.assertTrue(MODULE.verify_previous_source(self.store,candidate,self.profile))
        self.result['success']=False;self.write_result()
        with self.assertRaises(ValueError):MODULE.verify_previous_source(self.store,candidate,self.profile)
        (self.origin/'result.json').unlink()
        with self.assertRaises(OSError):MODULE.verify_previous_source(self.store,candidate,self.profile)


class RecoveryLogTests(unittest.TestCase):
    def test_final_log_rejects_duplicate_replacement_truncation_and_partial_line(self):
        content=(b'[X4LAN] AUTH_RECOVERY REQUEST\n[X4LAN] AUTH_MARKER load INSPECTED '+
                 MARKER.encode()+b'\n[X4LAN] AUTH_RECOVERY PAUSED\n')
        for change in ('duplicate','replacement','truncation','partial'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'engine-output.log'; path.write_bytes(content)
                watch=MODULE.recovery.RecoveryWatch(path,MARKER)
                self.assertTrue(watch.poll()); self.assertEqual(watch.stage,3)
                if change == 'duplicate':
                    with path.open('ab') as stream: stream.write(b'[X4LAN] AUTH_RECOVERY PAUSED\n')
                elif change == 'replacement':
                    original=path.with_name('old.log'); path.rename(original); path.write_bytes(content)
                elif change == 'truncation': path.write_bytes(b'')
                else:
                    with path.open('ab') as stream: stream.write(b'partial log line')
                with self.assertRaises(ValueError): MODULE.verify_final_recovery(watch)


class IntegratedLoopTest(unittest.TestCase):
    def test_witness_confirmation_requires_final_evidence_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'store').mkdir();store=CheckpointStore(root/'store')
            source=root/'save.xml.gz';source.write_bytes(gzip.compress(XML.encode()))
            candidate=store.publish(source,marker=MARKER)
            for result,remaining,errors in (({'success':False},[],[]),
                                            ({'success':True},None,[]),
                                            ({'success':True},[123],[]),
                                            ({'success':True},[],['cleanup failed'])):
                with self.subTest(result=result,remaining=remaining,errors=errors):
                    with self.assertRaises(ValueError):
                        MODULE.confirm_witness_after_cleanup(store,candidate,result,remaining,errors)
                    self.assertFalse((root/'store/CONFIRMED').exists())
            MODULE.confirm_witness_after_cleanup(store,candidate,{'success':True},[],[])
            self.assertEqual(store.latest_marked_confirmed(),candidate)

    def test_two_joins_and_last_disconnect_saves_with_real_coordinator(self):
        # Real control sockets/coordinator and save store, fake X4 and client claims.
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'store').mkdir(); store=CheckpointStore(root/'store')
            service=FileService('a'*32, slots=(1,)).start()
            listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            listener.bind(('127.0.0.1',0)); listener.listen(4)
            engine=Engine(root); world=WorldCoordinator('a'*32,engine,store,SaveOffers(service,store),participants=Participants())
            control=ExperimentalTCPControl(TrustedMarkerLoadSession(world,enabled=True),enabled=True)
            host=ExperimentalLocalHost(world,control,service,enabled=True)
            stop=threading.Event(); errors=[]
            def wait_for(predicate):
                deadline=time.monotonic()+4
                while not predicate():
                    if time.monotonic()>=deadline: raise TimeoutError('fake client wait timed out')
                    time.sleep(.005)
            def read_frame(conn):
                out=b''
                while not out.endswith(b'\n'):
                    data=conn.recv(1)
                    if not data: raise RuntimeError('control closed')
                    out+=data
                return out[:-1]
            def client():
                try:
                    for n in (1,2):
                        with socket.create_connection(listener.getsockname(),timeout=2) as conn:
                            conn.settimeout(2); conn.sendall(offer_request())
                            while True:
                                frame=read_frame(conn)
                                if json.loads(frame).get('kind')!='not_ready': break
                                time.sleep(.01); conn.sendall(offer_request())
                            bound=decode_bound_offer(frame)
                            conn.sendall(encode_load_claim(claim_for(bound.offer))+b'\n')
                            if json.loads(read_frame(conn))['kind']!='accepted': raise ValueError('claim refused')
                            wait_for(lambda: engine.calls.count('resume')>=n)
                            if n == 2:
                                stop.set()
                                if conn.recv(1) != b'': raise ValueError('shutdown did not close client')
                                return
                        wait_for(lambda: engine.calls.count('save')>=n+1 and world.session.state=='paused')
                except BaseException as error:
                    errors.append(error); stop.set()
            worker=threading.Thread(target=client); worker.start()
            try:
                counts=MODULE.serve(listener,host,deadline=time.monotonic()+5,
                                    check=lambda: None,should_stop=stop.is_set,tick_interval=.01)
                saved=MODULE.settle_shutdown(control,world,store,lambda: None)
                worker.join(2)
                self.assertFalse(worker.is_alive()); self.assertFalse(errors)
                self.assertEqual(counts,{'accepted_connections':2,'admitted_connections':2})
                self.assertEqual(engine.calls,['pause','save','resume','pause','save',
                                               'resume','pause','save'])
                self.assertEqual(world.session.players,())
                self.assertEqual(world.session.state,'paused')
                self.assertEqual(saved,store.latest_marked_confirmed())
            finally:
                stop.set(); worker.join(2)
                if not (control._closed or control._failed): control.close()
                listener.close(); service.close(); service.thread.join(2)


if __name__ == '__main__': unittest.main()
