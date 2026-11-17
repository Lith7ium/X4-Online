"""Two admitted TCP peers; simulated clients and grants, no X4 or writes."""
import json
import select
import socket
import threading
import unittest
from tests import test_authority_experimental_tcp_participants as fixture
from authority.experimental_tcp_client_authority_motion import ExperimentalTCPClientAuthorityMotion
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import motion_digest


class TwoPeerAuthority(unittest.TestCase):
    def setUp(self):
        self.case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.stop=threading.Event();self.errors=[];self.requests=[];self.clients=[];self.threads=[]
        self.before_authority_reply=None
        for handle in (1,2):
            client=self.case.connect();self.clients.append(client)
        for client in self.clients:self.case.offer_and_claim(client)
        for handle,client in enumerate(self.clients,1):
            client.settimeout(.1)
            def serve(conn=client, participant=handle):
                data=b'';sequence=0
                try:
                    while not self.stop.is_set():
                        try:chunk=conn.recv(8192)
                        except socket.timeout:continue
                        if not chunk:break
                        data+=chunk
                        while b'\n' in data:
                            raw,data=data.split(b'\n',1);request=json.loads(raw)
                            if request['kind']=='accepted':continue
                            if request['kind']=='participant_command':
                                reply=dict(request,kind='participant_receipt',status='confirmed')
                            else:
                                assert request['kind']=='authority_motion_pull'
                                self.requests.append((participant,request))
                                assert request['connection_handle']==participant
                                sequence+=1;grant=request['grant']
                                sample={'version':2 if participant==2 else 1,'epoch':grant['epoch'],
                                    'generation':grant['generation'],'index':grant['index'],'sequence':sequence,
                                    'sector_macro':grant['sector_macro'],'source_time':float(sequence),
                                    'x':float(participant),'y':0.,'z':0.,'velocity':None}
                                if participant==2:sample.update(orientation={'yaw':.1,'pitch':.2,'roll':.3},angular_rate=None)
                                reply={k:request[k] for k in ('version','connection_handle','session_epoch','incarnation','request_id','grant')}
                                reply.update(kind='authority_motion_result',sample=sample,sample_sha256=motion_digest(sample))
                                if self.before_authority_reply:self.before_authority_reply(participant)
                            conn.sendall(json.dumps(reply,separators=(',',':')).encode()+b'\n')
                except BaseException as error:
                    if not self.stop.is_set():self.errors.append(error)
            thread=threading.Thread(target=serve);thread.start();self.threads.append(thread)
        self.addCleanup(self.finish)
        self.case.host.tick(.1)
        self.delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=1)
        members=self.delivery.membership()
        self.grants=[{'session_epoch':'a'*32,'epoch':'b'*32,'generation':'c'*32,'index':slot+2,
                      'sector_macro':'sector_'+str(slot),'token':str(slot)*32,'incarnation':members[slot-1]['incarnation']}
                     for slot in (1,2)]
    def finish(self):
        self.stop.set()
        for thread in self.threads:thread.join(2)
        self.assertFalse(any(thread.is_alive() for thread in self.threads));self.assertEqual(self.errors,[])
    def owner(self,handle,grant=None):
        grant=grant or self.grants[handle-1]
        return ExperimentalTCPClientAuthorityMotion(self.delivery,enabled=True,grant=grant,guard=lambda value:value==grant,
                                                    connection_handle=handle)
    def test_independent_sequences_and_versions_for_two_handles(self):
        first=self.owner(1);second=self.owner(2)
        for owner,index,version,sequence in ((first,3,1,1),(second,4,2,1),(first,3,1,2),(second,4,2,2)):
            sample=owner.pull();self.assertEqual((sample['index'],sample['version'],sample['sequence']),(index,version,sequence))
        self.assertEqual([h for h,_ in self.requests],[1,2,1,2])
        self.assertEqual([r['request_id'] for _,r in self.requests],[1,1,2,2])
        self.assertIsNone(self.case.control._reader_lease)
    def test_wrong_incarnation_fences_before_send(self):
        grant={**self.grants[0],'incarnation':'f'*32}
        owner=self.owner(1,grant)
        with self.assertRaises(RuntimeError):owner.pull()
        self.assertEqual(self.requests,[]);self.assertTrue(self.case.host._failed)
    def test_default_requires_single_peer_and_cannot_mix_ownership(self):
        owner=ExperimentalTCPClientAuthorityMotion(self.delivery,enabled=True,grant=self.grants[0],guard=lambda _:True)
        with self.assertRaises(ValueError):self.owner(2)
        with self.assertRaises(RuntimeError):owner.pull()
        self.assertEqual(self.requests,[])
    def test_duplicate_target_or_grant_is_rejected(self):
        self.owner(1)
        with self.assertRaises(ValueError):self.owner(1)
        with self.assertRaises(ValueError):self.owner(2,{**self.grants[1],'token':self.grants[0]['token']})
        with self.assertRaises(ValueError):self.owner(2,{**self.grants[1],'index':self.grants[0]['index']})
        with self.assertRaises(ValueError):
            ExperimentalTCPClientAuthorityMotion(self.delivery,enabled=True,grant=self.grants[1],guard=lambda _:True)
        self.assertFalse(self.case.host._failed)
    def test_other_peer_unsolicited_input_fences_before_dispatch(self):
        owner=self.owner(1)
        self.clients[1].sendall(b'unexpected\n')
        other=next(conn for conn,peer in self.case.control._peers.items() if peer['handle']==2)
        self.assertIn(other,select.select([other],[],[],1)[0])
        with self.assertRaises(RuntimeError):owner.pull()
        self.assertEqual(self.requests,[]);self.assertTrue(self.case.host._failed)
    def test_active_reader_lease_refuses_another_pull(self):
        owner=self.owner(2);lease=object();self.case.control._reader_lease=lease
        try:
            with self.assertRaises(RuntimeError):owner.pull()
            self.assertEqual(self.requests,[]);self.assertIs(self.case.control._reader_lease,lease)
        finally:self.case.control._reader_lease=None

    def test_other_peer_input_during_exchange_fences_after_dispatch(self):
        owner=self.owner(1)
        sent=threading.Event()
        other=next(conn for conn,peer in self.case.control._peers.items() if peer['handle']==2)
        def interfere(participant):
            self.assertEqual(participant,1)
            self.clients[1].sendall(b'unexpected\n')
            self.assertIn(other,select.select([other],[],[],1)[0])
            sent.set()
        self.before_authority_reply=interfere
        with self.assertRaises(RuntimeError):owner.pull()
        self.assertTrue(sent.wait(1))
        self.assertEqual([handle for handle,_ in self.requests],[1])
        self.assertTrue(self.case.host._failed)

    def test_swallowed_cross_owner_reentry_fences_first_pull(self):
        second=self.owner(2)
        def reenter(_grant):
            try:second.pull()
            except RuntimeError:pass
            return True
        first=ExperimentalTCPClientAuthorityMotion(self.delivery,enabled=True,grant=self.grants[0],
                                                   guard=reenter,connection_handle=1)
        with self.assertRaises(RuntimeError):first.pull()
        self.assertEqual(self.requests,[])
        self.assertTrue(self.case.host._failed)

    def test_orderly_departure_preserves_survivor_and_revokes_old_grant(self):
        first=self.owner(1);second=self.owner(2)
        self.assertEqual(first.pull()['sequence'],1)
        self.assertEqual(second.pull()['sequence'],1)
        self.assertTrue(self.delivery.suspend_client_authority())
        with self.assertRaisesRegex(RuntimeError,'suspended'):second.pull()
        connection=next(conn for conn,peer in self.case.control._peers.items() if peer['handle']==1)
        self.case.control._drop(connection)
        with self.assertRaisesRegex(RuntimeError,'revoked'):first.pull()
        with self.assertRaisesRegex(ValueError,'retired authority grant'):
            self.owner(1)
        self.assertTrue(self.delivery.resume_client_authority())
        self.assertEqual(second.pull()['sequence'],2)
        # A new client joins while the surviving owner and its sequence persist.
        self.assertTrue(self.delivery.suspend_client_authority())
        newcomer=self.case.connect();self.clients.append(newcomer)
        self.case.host.tick(.1)  # Pause the surviving client before saving the join baseline.
        self.case.offer_and_claim(newcomer)
        newcomer.settimeout(.1)
        def serve_newcomer():
            data=b'';sequence=0
            try:
                while not self.stop.is_set():
                    try:chunk=newcomer.recv(8192)
                    except socket.timeout:continue
                    if not chunk:break
                    data+=chunk
                    while b'\n' in data:
                        raw,data=data.split(b'\n',1);request=json.loads(raw)
                        if request['kind']=='accepted':continue
                        if request['kind']=='participant_command':
                            reply=dict(request,kind='participant_receipt',status='confirmed')
                        else:
                            assert request['kind']=='authority_motion_pull' and request['connection_handle']==3
                            sequence+=1;grant=request['grant']
                            sample={'version':1,'epoch':grant['epoch'],'generation':grant['generation'],
                                    'index':grant['index'],'sequence':sequence,'sector_macro':grant['sector_macro'],
                                    'source_time':float(sequence),'x':3.,'y':0.,'z':0.,'velocity':None}
                            reply={key:request[key] for key in ('version','connection_handle','session_epoch',
                                                                'incarnation','request_id','grant')}
                            reply.update(kind='authority_motion_result',sample=sample,sample_sha256=motion_digest(sample))
                        newcomer.sendall(json.dumps(reply,separators=(',',':')).encode()+b'\n')
            except BaseException as error:
                if not self.stop.is_set():self.errors.append(error)
        thread=threading.Thread(target=serve_newcomer);thread.start();self.threads.append(thread)
        self.case.host.tick(.1)
        grant={**self.grants[0],'token':'3'*32,'incarnation':'f'*32}
        replacement=self.owner(3,grant)
        self.assertTrue(self.delivery.resume_client_authority())
        self.assertEqual(second.pull()['sequence'],3)
        self.assertEqual(replacement.pull()['sequence'],1)
        self.assertFalse(self.case.host._failed)

    def test_unexpected_departure_fences_the_host_and_revokes_grant(self):
        first=self.owner(1);self.owner(2)
        connection=next(conn for conn,peer in self.case.control._peers.items() if peer['handle']==1)
        with self.assertRaisesRegex(RuntimeError,'control channel faulted'):
            self.case.control._drop(connection)
        self.assertTrue(self.case.host._failed)
        with self.assertRaisesRegex(RuntimeError,'revoked'):first.pull()

    def test_explicit_revoke_retires_original_identity_if_grant_changed(self):
        first=self.owner(1);self.owner(2)
        self.assertTrue(self.delivery.suspend_client_authority())
        original_token=first._grant['token']
        original_incarnation=first._grant['incarnation']
        first._grant['token']='9'*32
        with self.assertRaisesRegex(RuntimeError,'changed during revocation'):
            first.revoke()
        self.assertIn(original_token,self.delivery._retired_authority_tokens)
        self.assertIn(original_incarnation,self.delivery._retired_authority_incarnations)
        self.assertTrue(self.case.host._failed)

    def test_disconnect_retires_original_identity_if_grant_changed(self):
        first=self.owner(1);self.owner(2)
        self.assertTrue(self.delivery.suspend_client_authority())
        original_token=first._grant['token']
        original_incarnation=first._grant['incarnation']
        first._grant['incarnation']='9'*32
        connection=next(conn for conn,peer in self.case.control._peers.items() if peer['handle']==1)
        with self.assertRaisesRegex(RuntimeError,'control channel faulted'):
            self.case.control._drop(connection)
        self.assertIn(original_token,self.delivery._retired_authority_tokens)
        self.assertIn(original_incarnation,self.delivery._retired_authority_incarnations)
        self.assertTrue(self.case.host._failed)

    def test_cyclic_grant_is_retired_before_owner_is_fenced(self):
        first=self.owner(1);self.owner(2)
        self.assertTrue(self.delivery.suspend_client_authority())
        original_token=first._grant['token']
        original_incarnation=first._grant['incarnation']
        first._grant['cycle']=first._grant
        with self.assertRaisesRegex(RuntimeError,'changed during revocation'):
            first.revoke()
        self.assertIn(original_token,self.delivery._retired_authority_tokens)
        self.assertIn(original_incarnation,self.delivery._retired_authority_incarnations)
        self.assertTrue(self.case.host._failed)

    def test_suspend_refuses_busy_reader_without_releasing_it(self):
        self.owner(1);self.owner(2)
        lease=object();self.case.control._reader_lease=lease
        try:
            with self.assertRaises(RuntimeError):self.delivery.suspend_client_authority()
            self.assertIs(self.case.control._reader_lease,lease)
            self.assertFalse(self.delivery._authority_suspended)
        finally:self.case.control._reader_lease=None

    def test_suspend_fences_unread_peer_input(self):
        self.owner(1);self.owner(2)
        self.clients[1].sendall(b'unexpected\n')
        connection=next(conn for conn,peer in self.case.control._peers.items() if peer['handle']==2)
        self.assertIn(connection,select.select([connection],[],[],1)[0])
        with self.assertRaisesRegex(RuntimeError,'unexpected input'):
            self.delivery.suspend_client_authority()
        self.assertTrue(self.case.host._failed)
        self.assertFalse(self.delivery._authority_suspended)

    def test_release_requires_departure_and_does_not_revive_retired_tokens(self):
        first=self.owner(1);second=self.owner(2)
        self.assertTrue(self.delivery.suspend_client_authority())
        with self.assertRaisesRegex(RuntimeError,'cannot be released'):
            self.delivery.release_client_authority()
        for handle in (1,2):
            connection=next(conn for conn,peer in self.case.control._peers.items() if peer['handle']==handle)
            self.case.control._drop(connection)
        self.assertTrue(self.delivery.release_client_authority())
        self.assertIsNone(self.case.control._job_delivery_owner)
        replacement=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=1)
        for stale_grant in (self.grants[0], {**self.grants[0],'token':'9'*32},
                            {**self.grants[0],'incarnation':'9'*32}):
            with self.subTest(stale_grant=stale_grant), self.assertRaisesRegex(ValueError,'retired authority grant'):
                ExperimentalTCPClientAuthorityMotion(replacement,enabled=True,grant=stale_grant,
                                                      guard=lambda _:True,connection_handle=1)
        with self.assertRaisesRegex(RuntimeError,'revoked'):first.pull()
        with self.assertRaisesRegex(RuntimeError,'revoked'):second.pull()

if __name__=='__main__':unittest.main()
