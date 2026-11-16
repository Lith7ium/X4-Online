"""Whole experimental hook with synthetic game and actual TCP/UDP/helper."""
from pathlib import Path
import gzip
import os
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev'),str(ROOT/'tests')]
import authority_tcp_native_live as subject
import authority_remote_load_pair_live as remote
from authority.checkpoints import CheckpointStore
from authority.save_transfer import SaveOffers
from authority.world import WorldCoordinator
from lockstep.launcher.joinfiles import FileService
from test_authority_experimental_local_host import Engine
from test_authority_trusted_marker_load_session import XML, MARKER


class FreshEngine(Engine):
    def save(self):
        self.calls.append('save')
        if getattr(self,'fail_final_save',False) and self.calls.count('save')==3:
            raise TimeoutError('uncertain final save')
        self.pending_marker = f'{self.calls.count("save"):032x}'
        path = self.root/'source.gz'
        path.write_bytes(gzip.compress(XML.replace(MARKER,self.pending_marker).encode()))
        return path


class HookIntegrationTest(unittest.TestCase):
    def test_eof_check_refuses_unexpected_data(self):
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.bind(('127.0.0.1',0));listener.listen(1)
        client=socket.create_connection(listener.getsockname(),timeout=1);server,_=listener.accept()
        try:
            client.sendall(b'x')
            with self.assertRaisesRegex(RuntimeError,'unexpected control data'):
                subject.await_eof(server,time.monotonic()+3,lambda:True)
            self.assertEqual(server.recv(1),b'x')
            client.shutdown(socket.SHUT_WR)
            subject.await_eof(server,time.monotonic()+3,lambda:True)
        finally: client.close();server.close();listener.close()

    def test_bridge_timeout_is_capped_and_restored_on_failure(self):
        bridge=Mock();bridge._timeout=130
        def fail():
            self.assertLess(bridge._timeout, 20)
            raise RuntimeError('uncertain bridge')
        bridge.pause.side_effect=fail
        wrapped=subject.DeadlineEngine(bridge,time.monotonic()+20)
        with self.assertRaisesRegex(RuntimeError,'uncertain bridge'): wrapped.pause()
        self.assertEqual(bridge._timeout,130)

    def test_failure_before_base_ownership_closes_participant(self):
        participant=Mock()
        args=SimpleNamespace(timeout=10)
        original=subject.marked.MarkedParticipant
        with patch.object(subject,'TCPMarkedParticipant',return_value=participant), \
             patch.object(subject.marked,'run',side_effect=ValueError('early failure')):
            with self.assertRaisesRegex(ValueError,'early failure'): subject.run(args)
        participant.cleanup_before_owned_processes.assert_called_once()
        participant.close.assert_called_once()
        self.assertIs(subject.marked.MarkedParticipant, original)

    def test_helper_stop_failure_still_closes_all_communications(self):
        participant=subject.TCPMarkedParticipant(time.monotonic()+10)
        helper=Mock();helper.stop.side_effect=RuntimeError('unconfirmed')
        participant.helpers=[helper]
        connections=[Mock(),Mock(),Mock(),Mock()]
        participant.ipc,participant.client_tcp,participant.second,participant.server_tcp=connections
        udp=participant.sock;participant.sock=Mock()
        control=Mock();control._closed=False;control._failed=False;participant.control=control
        try:
            with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):
                participant.cleanup_before_owned_processes()
            for conn in connections: conn.close.assert_called_once()
            control.close.assert_called_once()
            participant.sock.close.assert_called_once()
        finally:
            participant.sock=udp
            participant.close()

    def test_real_offer_claim_and_helper_control_with_fake_game(self):
        self.exercise_fake_game(last_disconnect=False)

    def test_first_resume_only_stops_helper_without_second_join(self):
        self.exercise_fake_game(last_disconnect=False,first_resume_only=True)

    def test_remote_owner_handoff_reaches_worker_before_resume(self):
        self.exercise_fake_game(last_disconnect=False, first_resume_only=True, remote_owner=True)

    def test_incompatible_resume_options_refused_before_socket_creation(self):
        for kwargs in ({'last_disconnect':True,'first_resume_only':True},
                       {'last_disconnect':1},{'first_resume_only':1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                subject.TCPMarkedParticipant(time.monotonic()+1,**kwargs)

    def test_last_tcp_disconnect_pauses_and_confirms_fresh_marker(self):
        self.exercise_fake_game(last_disconnect=True,delay_eof=True)

    def test_failed_last_save_leaves_indeterminate_server_result(self):
        self.exercise_fake_game(last_disconnect=True,fail_final_save=True)

    def exercise_fake_game(self, *, last_disconnect,delay_eof=False,fail_final_save=False,first_resume_only=False,
                           remote_owner=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'store').mkdir(); (root/'client/save').mkdir(parents=True)
            (root/'game').mkdir(); (root/'game/X4').symlink_to('/proc/self/exe')
            store=CheckpointStore(root/'store')
            service=FileService('f'*32,slots=(1,)).start()
            engine=FreshEngine(root);engine._timeout=5
            engine.fail_final_save=fail_final_save
            world=WorldCoordinator('a'*32,engine,store,SaveOffers(service,store))
            participant_type = remote.RemoteParticipant if remote_owner else subject.TCPMarkedParticipant
            participant=participant_type(time.monotonic()+15,last_disconnect=last_disconnect,first_resume_only=first_resume_only)
            udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0));udp.settimeout(.05)
            stop=threading.Event();commands=[]
            destination=participant.sock.getsockname()
            def fake_client():
                while not stop.is_set():
                    udp.sendto(('HELLO|'+participant.lease+'|'+'a'*32).encode(),destination)
                    try: data,peer=udp.recvfrom(1024)
                    except socket.timeout: continue
                    except OSError: return
                    row=data.decode().split('|')
                    if len(row)!=5 or row[0]!='CMD': continue
                    _,lease,epoch,number,operation=row;commands.append(operation)
                    udp.sendto('|'.join(('RECEIPT',lease,epoch,number,operation,'confirmed')).encode(),peer)
            thread=None
            try:
                handle=participant.join(world);world.step();world.step()
                ticket,target=participant.offer_and_download(world,service,handle,root,root/'client')
                identity=(os.getpid(),subject.marked.base.live.start_ticks(os.getpid()))
                thread=threading.Thread(target=fake_client);thread.start()
                result={}; proc=object()
                original_poll=participant.control.poll;delays={'second':0,'last':0}
                def poll(timeout):
                    if delay_eof and participant.second is None and world.session.state=='saving' and len(world.session.players)==2 and delays['second']<2:
                        self.assertEqual(engine.calls.count('save'),1)
                        delays['second']+=1;return
                    if delay_eof and participant.helpers and participant.helpers[0].proc.returncode is not None and world.session.state=='running' and delays['last']<2:
                        self.assertEqual(len(world.session.players),1)
                        delays['last']+=1;return
                    return original_poll(timeout)
                def run_hook():
                    participant.on_ready(world=world,handle=handle,ticket=ticket,target=target,
                        server_identity=identity,server_proc=proc,server_started=identity[1],
                        client_identity=identity,client_proc=proc,client_started=identity[1],
                        game=root/'game',out=root,deadline=time.monotonic()+10,result=result,
                        check_protected=lambda:True)
                with patch.object(participant,'verify_logs',wraps=participant.verify_logs) as verify_hook, \
                     patch.object(subject.marked,'observe_logs') as verify_logs, \
                     patch.object(subject.marked.base.client,'game_identity',return_value=identity), \
                     patch.object(participant.control,'poll',side_effect=poll):
                    if fail_final_save:
                        with self.assertRaisesRegex(TimeoutError,'uncertain final save'): run_hook()
                    else: run_hook()
                self.assertEqual(verify_hook.call_count,2)
                self.assertEqual(verify_logs.call_count,2)
                if fail_final_save:
                    self.assertTrue(result['last_eof_observed'])
                    self.assertTrue(result['last_departure_pause_confirmed'])
                    self.assertEqual(result['server_state'],'indeterminate')
                    self.assertNotIn('last_departure_checkpoint_confirmed',result)
                    self.assertEqual(world.session.state,'faulted')
                    return
                self.assertTrue(result['client_admitted']);self.assertTrue(result['tcp_claim_used'])
                self.assertTrue(result['native_server_and_client_resume_confirmed'])  # synthetic only
                if first_resume_only:
                    self.assertFalse(result['simulated_second_join'])
                    self.assertNotIn('native_server_and_client_pause_confirmed',result)
                    self.assertEqual(world.session.state,'running')
                    self.assertEqual(len(world.session.players),1)
                    self.assertEqual(engine.calls.count('save'),1)
                else:
                    self.assertTrue(result['native_server_and_client_pause_confirmed'])
                self.assertTrue(result['helper_clean_exit'])
                self.assertEqual(commands,['pause','resume'] if first_resume_only else
                    (['pause','resume','pause','resume'] if last_disconnect else ['pause','resume','pause']))
                if last_disconnect:
                    self.assertTrue(result['simulated_client_disconnect'])
                    self.assertTrue(result['last_eof_observed'])
                    self.assertTrue(result['last_departure_pause_confirmed'])
                    self.assertTrue(result['last_departure_checkpoint_confirmed'])
                    self.assertTrue(result['marker_changed'])
                    self.assertEqual(result['last_checkpoint_id'],store.latest_marked_confirmed().checkpoint_id)
                    self.assertEqual(world.session.state,'paused')
                    self.assertEqual(world.session.players,())
                    self.assertIsNone(world.session.pending)
                    self.assertEqual(engine.calls.count('save'),3)
                    if delay_eof: self.assertEqual(delays,{'second':2,'last':2})
                self.assertTrue(all(h.proc.poll() is not None for h in participant.helpers))
            finally:
                stop.set()
                if thread is not None: thread.join(2)
                udp.close()
                participant.cleanup_before_owned_processes()
                participant.close()
                service.close();service.thread.join(2)


if __name__=='__main__': unittest.main()
