"""Whole experimental hook with synthetic game and actual TCP/UDP/helper."""
from pathlib import Path
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
from authority.checkpoints import CheckpointStore
from authority.save_transfer import SaveOffers
from authority.world import WorldCoordinator
from lockstep.launcher.joinfiles import FileService
from test_authority_experimental_local_host import Engine


class HookIntegrationTest(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'store').mkdir(); (root/'client/save').mkdir(parents=True)
            (root/'game').mkdir(); (root/'game/X4').symlink_to('/proc/self/exe')
            store=CheckpointStore(root/'store')
            service=FileService('f'*32,slots=(1,)).start()
            engine=Engine(root);engine._timeout=5
            world=WorldCoordinator('a'*32,engine,store,SaveOffers(service,store))
            participant=subject.TCPMarkedParticipant(time.monotonic()+15)
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
                with patch.object(subject.marked,'observe_logs'), \
                     patch.object(subject.marked.base.client,'game_identity',return_value=identity):
                    participant.on_ready(world=world,handle=handle,ticket=ticket,target=target,
                        server_identity=identity,server_proc=proc,server_started=identity[1],
                        client_identity=identity,client_proc=proc,client_started=identity[1],
                        game=root/'game',out=root,deadline=time.monotonic()+10,result=result,
                        check_protected=lambda:True)
                self.assertTrue(result['client_admitted']);self.assertTrue(result['tcp_claim_used'])
                self.assertTrue(result['native_server_and_client_resume_confirmed'])  # synthetic only
                self.assertTrue(result['native_server_and_client_pause_confirmed'])
                self.assertTrue(result['helper_clean_exit'])
                self.assertEqual(commands,['pause','resume','pause'])
                self.assertTrue(all(h.proc.poll() is not None for h in participant.helpers))
            finally:
                stop.set()
                if thread is not None: thread.join(2)
                udp.close()
                participant.cleanup_before_owned_processes()
                participant.close()
                service.close();service.thread.join(2)


if __name__=='__main__': unittest.main()
