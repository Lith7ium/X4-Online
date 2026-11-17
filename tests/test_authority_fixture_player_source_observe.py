"""Private fixture observer over real TCP and simulated clients; no X4."""
import copy
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_fixture_player_source_observe as observer
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from tests import test_authority_experimental_tcp_participants as fixture


class Controller:
    def pause(self, handles):return True
    def resume(self, handles):return True


class ObserverTCP(unittest.TestCase):
    def test_two_actual_tcp_adapters_return_only_rate_bearing_samples(self):
        case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        case.setUp();self.addCleanup(case.doCleanups)
        clients=[case.connect(),case.connect()]
        for client in clients:case.offer_and_claim(client)
        grants={handle:{'session_epoch':'a'*32,'epoch':'b'*32,'generation':'c'*32,'index':handle+2,
                        'sector_macro':'sector_'+str(handle),'token':str(handle)*32,'incarnation':str(handle+2)*32}
                for handle in (1,2)}
        stop=threading.Event();errors=[];threads=[]
        def serve(conn,handle):
            try:
                conn.settimeout(2);data=b''
                while not data.endswith(b'\n'):data+=conn.recv(1)
                assert json.loads(data)['kind']=='accepted'
                sequence=0;grant=grants[handle]
                def pull():
                    nonlocal sequence
                    sequence+=1
                    return {'version':2,'epoch':grant['epoch'],'generation':grant['generation'],'index':grant['index'],
                        'sequence':sequence,'sector_macro':grant['sector_macro'],'source_time':float(sequence),
                        'x':float(sequence),'y':float(handle),'z':0.,
                        'velocity':None if sequence==1 else {'x':1.,'y':0.,'z':0.},
                        'orientation':{'yaw':0.,'pitch':0.,'roll':0.},
                        'angular_rate':None if sequence==1 else {'yaw':0.,'pitch':0.,'roll':0.}}
                app=ExperimentalTCPParticipantClient(conn,Controller(),enabled=True,epoch='a'*32,handle=handle,timeout=2,
                    authority_grant=grant,authority_guard=lambda value:value==grant,pull_authority_motion=pull)
                while not stop.is_set():app.poll(.05)
                app.close()
            except BaseException as error:
                if not stop.is_set():errors.append(error)
        for handle,client in enumerate(clients,1):
            thread=threading.Thread(target=serve,args=(client,handle));thread.start();threads.append(thread)
        def finish():
            stop.set()
            for thread in threads:thread.join(2)
            self.assertFalse(any(thread.is_alive() for thread in threads));self.assertEqual(errors,[])
        self.addCleanup(finish)
        case.host.tick(.1)
        progress = {}; boundaries = []
        result=observer.observe(host=case.host,world=case.world,grants=grants,verify=lambda:None,
                                deadline=time.monotonic()+5,operation_timeout=2,enabled=True,
                                verify_transaction_boundary=lambda: boundaries.append(True) or True, progress=progress)
        self.assertEqual(len(boundaries), 12)
        self.assertEqual(progress, {
            1: {'registry_index': 3, 'pulls_attempted': 3, 'samples_received': 3, 'samples_with_complete_rates': 2, 'pulls_without_post_boundary': 0},
            2: {'registry_index': 4, 'pulls_attempted': 3, 'samples_received': 3, 'samples_with_complete_rates': 2, 'pulls_without_post_boundary': 0}})
        self.assertTrue(result['fixture_player_samples_observed'])
        self.assertFalse(result['server_x4_motion_applied'])
        self.assertEqual([row['registry_index'] for row in result['players']],[3,4])
        for row in result['players']:
            self.assertEqual([sample['sequence'] for sample in row['samples']],[2,3])
            self.assertTrue(all(sample['velocity'] is not None and sample['angular_rate'] is not None for sample in row['samples']))
        serialized=json.dumps(result)
        for grant in grants.values():
            for secret in ('epoch','generation','token','incarnation','session_epoch'):
                self.assertNotIn(grant[secret],serialized)

    def test_boundary_failure_fences_and_retains_nonsecret_progress(self):
        from types import SimpleNamespace
        for failing_call in (1, 2):
            with self.subTest(failing_call=failing_call):
                session = SimpleNamespace(world_epoch='a'*32, players=((1,'a'),(2,'b')),
                    ready_players=((1,'a'),(2,'b')), state='running', pending=None)
                world = SimpleNamespace(session=session)
                host = SimpleNamespace(_world=world, _failed=False)
                grant = {'session_epoch':'a'*32, 'epoch':'b'*32, 'generation':'c'*32, 'index':3,
                         'sector_macro':'sector_1', 'token':'1'*32, 'incarnation':'2'*32}
                grants = {1:grant, 2:{**grant,'index':4,'token':'4'*32,'incarnation':'5'*32}}
                trace = []; progress = {}; deliveries = []
                class Delivery:
                    def __init__(self,*args,**kwargs): self._failed=False; deliveries.append(self)
                    def bind_test_incarnations(self, bindings, enabled=False): return True
                class Owner:
                    def __init__(self,delivery,**kwargs): pass
                    def pull(self): trace.append('pull'); return {'untrusted': 'sample'}
                def boundary():
                    trace.append('boundary')
                    return trace.count('boundary') != failing_call
                def verify(): trace.append('check'); return True
                with patch.object(observer,'ExperimentalTCPJobDelivery',Delivery), \
                     patch.object(observer,'ExperimentalTCPClientAuthorityMotion',Owner):
                    with self.assertRaisesRegex(RuntimeError,'boundary guard failed'):
                        observer.observe(host=host,world=world,grants=grants,verify=verify,
                            verify_transaction_boundary=boundary,progress=progress,
                            deadline=time.monotonic()+2,enabled=True)
                self.assertTrue(host._failed and deliveries[0]._failed)
                self.assertEqual(trace[-1], 'check')
                self.assertEqual(trace.count('pull'), failing_call-1)
                self.assertEqual(progress[1]['pulls_attempted'], failing_call-1)
                self.assertEqual(progress[1]['samples_received'], failing_call-1)
                self.assertEqual(progress[1]['pulls_without_post_boundary'], failing_call-1)
                self.assertEqual(progress[1]['samples_with_complete_rates'], 0)
                self.assertEqual(progress[2]['registry_index'], 4)
                for key in ('epoch','generation','token','incarnation','session_epoch'):
                    self.assertNotIn(grant[key], json.dumps(progress))

    def test_failed_pull_records_unconfirmed_post_boundary(self):
        from types import SimpleNamespace
        session = SimpleNamespace(world_epoch='a'*32, players=((1,'a'),(2,'b')),
            ready_players=((1,'a'),(2,'b')), state='running', pending=None)
        world = SimpleNamespace(session=session); host = SimpleNamespace(_world=world, _failed=False)
        grant = {'session_epoch':'a'*32, 'epoch':'b'*32, 'generation':'c'*32, 'index':3,
                 'sector_macro':'sector_1', 'token':'1'*32, 'incarnation':'2'*32}
        grants = {1:grant, 2:{**grant,'index':4,'token':'4'*32,'incarnation':'5'*32}}
        calls = []; progress = {}; deliveries = []
        class Delivery:
            def __init__(self,*a,**k): self._failed=False; deliveries.append(self)
            def bind_test_incarnations(self,*a,**k): return True
        class Owner:
            def __init__(self,*a,**k): pass
            def pull(self): raise TimeoutError('injected pull timeout')
        def boundary(): calls.append('boundary'); return True
        with patch.object(observer,'ExperimentalTCPJobDelivery',Delivery), \
             patch.object(observer,'ExperimentalTCPClientAuthorityMotion',Owner):
            with self.assertRaises(TimeoutError):
                observer.observe(host=host,world=world,grants=grants,verify=lambda:True,
                    verify_transaction_boundary=boundary,progress=progress,
                    deadline=time.monotonic()+2,enabled=True)
        self.assertEqual(calls, ['boundary'])
        self.assertTrue(host._failed and deliveries[0]._failed)
        self.assertEqual(progress[1], {'registry_index':3,'pulls_attempted':1,'samples_received':0,
                                      'samples_with_complete_rates':0,'pulls_without_post_boundary':1})

    def test_boundary_context_mutation_refuses_pull(self):
        from types import SimpleNamespace
        session = SimpleNamespace(world_epoch='a'*32, players=((1,'a'),(2,'b')),
            ready_players=((1,'a'),(2,'b')), state='running', pending=None)
        world = SimpleNamespace(session=session); host = SimpleNamespace(_world=world, _failed=False)
        grant = {'session_epoch':'a'*32,'epoch':'b'*32,'generation':'c'*32,'index':3,
                 'sector_macro':'sector_1','token':'1'*32,'incarnation':'2'*32}
        grants = {1:grant,2:{**grant,'index':4,'token':'4'*32,'incarnation':'5'*32}}
        deliveries=[]
        class Delivery:
            def __init__(self,*a,**k):self._failed=False;deliveries.append(self)
            def bind_test_incarnations(self,*a,**k):return True
        class Owner:
            def __init__(self,*a,**k):pass
            def pull(self):raise AssertionError('pull must not start')
        def boundary():session.pending='changed';return True
        with patch.object(observer,'ExperimentalTCPJobDelivery',Delivery), \
             patch.object(observer,'ExperimentalTCPClientAuthorityMotion',Owner):
            with self.assertRaisesRegex(RuntimeError,'context changed'):
                observer.observe(host=host,world=world,grants=grants,verify=lambda:True,
                    verify_transaction_boundary=boundary,deadline=time.monotonic()+2,enabled=True)
        self.assertTrue(host._failed and deliveries[0]._failed)

    def test_bad_grants_and_expired_deadline_are_rejected_before_delivery(self):
        from types import SimpleNamespace
        session=SimpleNamespace(world_epoch='a'*32,players=((1,'a'),(2,'b')),ready_players=((1,'a'),(2,'b')),state='running',pending=None)
        world=SimpleNamespace(session=session);host=SimpleNamespace(_world=world)
        one={'session_epoch':'a'*32,'epoch':'b'*32,'generation':'c'*32,'index':3,
             'sector_macro':'sector_1','token':'1'*32,'incarnation':'2'*32}
        grants={1:one,2:{**one,'index':4,'token':'4'*32,'incarnation':'5'*32}}
        cases=[]
        duplicate=copy.deepcopy(grants);duplicate[2]['index']=3;cases.append((duplicate,time.monotonic()+2))
        wrong=copy.deepcopy(grants);wrong[2]['session_epoch']='f'*32;cases.append((wrong,time.monotonic()+2))
        cases.append((grants,time.monotonic()-1))
        with patch.object(observer,'ExperimentalTCPJobDelivery') as delivery:
            for candidate,deadline in cases:
                with self.subTest(grants=candidate,deadline=deadline),self.assertRaises((ValueError,TimeoutError)):
                    observer.observe(host=host,world=world,grants=candidate,verify=lambda:True,deadline=deadline,enabled=True)
            with self.assertRaises(ValueError):
                observer.observe(host=host,world=world,grants=grants,verify=lambda:True,deadline=time.monotonic()+2)
            delivery.assert_not_called()

    def test_bad_sample_after_binding_faults_both_delivery_and_host(self):
        from types import SimpleNamespace
        session=SimpleNamespace(world_epoch='a'*32,players=((1,'a'),(2,'b')),ready_players=((1,'a'),(2,'b')),state='running',pending=None)
        world=SimpleNamespace(session=session);host=SimpleNamespace(_world=world,_failed=False)
        grant={'session_epoch':'a'*32,'epoch':'b'*32,'generation':'c'*32,'index':3,
               'sector_macro':'sector_1','token':'1'*32,'incarnation':'2'*32}
        grants={1:grant,2:{**grant,'index':4,'token':'4'*32,'incarnation':'5'*32}}
        class Delivery:
            def __init__(self,*args,**kwargs):self._failed=False
            def bind_test_incarnations(self,bindings,enabled=False):return True
        class Owner:
            def __init__(self,delivery,**kwargs):pass
            def pull(self):
                return {'version':1,'epoch':'b'*32,'generation':'c'*32,'index':3,'sequence':1,
                        'sector_macro':'sector_1','source_time':1.,'x':0.,'y':0.,'z':0.,'velocity':None}
        holder=[]
        def make_delivery(*args,**kwargs):
            value=Delivery();holder.append(value);return value
        with patch.object(observer,'ExperimentalTCPJobDelivery',side_effect=make_delivery), \
             patch.object(observer,'ExperimentalTCPClientAuthorityMotion',Owner):
            with self.assertRaisesRegex(ValueError,'sample differs'):
                observer.observe(host=host,world=world,grants=grants,verify=lambda:True,
                                 deadline=time.monotonic()+2,enabled=True)
        self.assertTrue(host._failed);self.assertTrue(holder[0]._failed)


if __name__=='__main__':unittest.main()
