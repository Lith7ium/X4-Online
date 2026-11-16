"""Synthetic X4 peers with real local UDP/TCP and a pidfd-gated helper."""
import importlib.util
import socket
import shutil
import subprocess
import threading
import time
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pair_transfer',ROOT/'tools/dev/authority_sector_pair_transfer_live.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Transfer(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'),'compiler and LuaJIT required')
    def test_default_session_uses_real_adapter_and_driver(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_sector_pair_create_fake_x4.c',
                            '-o',str(lib)],cwd=ROOT,check=True,capture_output=True,timeout=10)
            subprocess.run(['luajit','tests/authority_sector_pair_session.lua',str(lib)],cwd=ROOT,
                           check=True,capture_output=True,timeout=5)

    def test_compiler_timeout_kills_group_and_reaps(self):
        proc=Mock(pid=98765,returncode=None)
        proc.wait.side_effect=[subprocess.TimeoutExpired('cc',30),-9]
        with patch.object(m.subprocess,'Popen',return_value=proc) as popen, patch.object(m.os,'killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):m.compile_net('/fake/cc',Path('/tmp/fake.so'))
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        kill.assert_called_once_with(98765,m.signal.SIGKILL)
        self.assertEqual(proc.wait.call_count,2)

    def test_unconfirmed_compiler_cleanup_retains_process_and_fails_closed(self):
        for fault in ('kill','reap'):
            with self.subTest(fault=fault):
                proc=Mock(pid=98765,returncode=None)
                proc.wait.side_effect=[subprocess.TimeoutExpired('cc',30),
                    subprocess.TimeoutExpired('cc',5) if fault=='reap' else -9]
                with patch.object(m.subprocess,'Popen',return_value=proc), patch.object(m.os,'killpg',
                    side_effect=OSError('unknown') if fault=='kill' else None):
                    with self.assertRaises(m.CompilerCleanupUnconfirmed) as caught:
                        m.compile_net('/fake/cc',Path('/tmp/fake.so'))
                self.assertIs(caught.exception.proc,proc)
                participant=m.PairTransferParticipant();participant.compiler_cleanup_error=caught.exception
                sock=Mock();helper=Mock();participant.sockets=[sock];participant.helpers=[helper]
                with self.assertRaises(m.CompilerCleanupUnconfirmed):participant.cleanup_before_owned_processes()
                sock.close.assert_called_once();helper.stop.assert_called_once()

    def test_cleanup_attempts_all_sockets_and_helper_after_error(self):
        participant=m.PairTransferParticipant()
        bad=Mock();bad.close.side_effect=OSError('close failed')
        good=Mock();helper=Mock();participant.sockets=[bad,good];participant.helpers=[helper]
        with self.assertRaisesRegex(RuntimeError,'pre-cleanup unconfirmed'):
            participant.cleanup_before_owned_processes()
        good.close.assert_called_once();helper.stop.assert_called_once()
        self.assertFalse(participant.closed)
        good.reset_mock()
        with self.assertRaisesRegex(RuntimeError,'post-cleanup unconfirmed'):
            participant.cleanup_after_owned_processes()
        good.close.assert_called_once()

    def test_helper_status_rejects_external_reap(self):
        participant=m.PairTransferParticipant()
        helper=Mock(pidfd=123);helper.proc.returncode=None
        with patch.object(m.signal,'getsignal',return_value=m.signal.SIG_DFL), \
             patch.object(m.os,'waitid',side_effect=ChildProcessError):
            with self.assertRaisesRegex(RuntimeError,'reaped externally'):
                participant._helper_status(helper)
        helper.proc.poll.assert_not_called()

    def test_private_overlay_uses_one_update_owner_and_archived_registry(self):
        with tempfile.TemporaryDirectory() as t:
            case=Path(t)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
            ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
            for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
            ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
                checkpoint_id=m.pair.base.archive.CHECKPOINT_ID,sha256=m.pair.base.archive.SHA256,
                attempt_id='b'*32,slot='save_009')
            base=m.pair.install(case,profile,ticket,'server','c'*32,['sector_a','sector_b'],120)
            registry=(md/'authority_ship_registry.xml').read_bytes()
            participant=m.PairTransferParticipant()
            try:
                extra=participant.install(case,profile,ticket,'server','c'*32,['sector_a','sector_b'],120)
                self.assertEqual((md/'authority_ship_registry.xml').read_bytes(),registry)
                self.assertIn(md/'authority_ship_create_receiver.xml',extra)
                self.assertIn(lab/'native/x4lan_net.so',extra)
                ready=(md/'authority_sector_pair_ready.xml').read_text()
                self.assertIn('not md.X4AuthorityShipCreateReceiver.State.$epoch?',ready)
                self.assertIn('not md.X4AuthorityShipCreateReceiver.State.$receipts?',ready)
                self.assertIn('$s1 != player.sector',ready)
                self.assertIn('$sector != player.sector',(md/'authority_ship_create_receiver.xml').read_text())
                owner=(ui/'authority_download_load_probe.lua').read_text()
                self.assertEqual(owner.count("SetScript('onUpdate'"),1)
                self.assertIn('X4LAN_SECTOR_PAIR_TICK()',owner)
                self.assertIn('X4LAN_PAIR_CREATE_TICK()',owner)
                self.assertIn(ui/'config.lua',base)
            finally:
                participant.cleanup_before_owned_processes();participant.cleanup_after_owned_processes()

    def run_fake(self,drop_check=False,duplicate_ready=False,fail_inspect=False):
        participant=m.PairTransferParticipant();stop=threading.Event();alive=threading.Event();alive.set();threads=[];order=[];errors=[]
        for role in ('server','client'):
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.setblocking(False)
            participant.sockets.append(sock)
            lease=('a' if role=='server' else 'b')*32
            participant.roles[role]={'sock':sock,'peer':None,'lease':lease,'events':[],
                'event_at':0,'pending':None,'counter':0}
            peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0));peer.settimeout(.1)
            def fake(role=role,sock=sock,peer=peer,lease=lease):
                prefix='|'.join(('PAIR',lease,role,participant.attempt,participant.epoch))
                cmd='|'.join(('CMD',lease,role,participant.attempt,participant.epoch))+'|'
                def send(msg):peer.sendto((prefix+'|'+msg).encode(),sock.getsockname())
                try:
                    send('READY')
                    if duplicate_ready and role=='server':send('READY')
                    while not stop.is_set():
                        try:data,_=peer.recvfrom(769)
                        except socket.timeout:continue
                        text=data.decode();assert text.startswith(cmd)
                        command=text[len(cmd):];order.append((role,command.split('|')[0]))
                        if command.startswith('CHECK|'):
                            if not (drop_check and role=='server'):send('CHECKED|'+command.split('|')[1])
                        elif command=='START':
                            if role=='client':send('AWAIT')
                            else:send('DESCRIPTOR|1|3|ship_arg_s_fighter_01_a_macro|sector_a|argon|7183|-400|100000|500')
                        elif command.startswith('DESCRIPTOR|') and role=='client':
                            if fail_inspect:alive.clear()
                            send('INSPECTED|1|3')
                        elif command=='ACK|1|3' and role=='server':send('FINISHED|1|3')
                        else:raise AssertionError(command)
                except BaseException as exc:
                    if not stop.is_set():errors.append(exc)
                finally:peer.close()
            thread=threading.Thread(target=fake,daemon=True);threads.append(thread);thread.start()
        context={'check':alive.is_set,'deadline':time.monotonic()+(1 if drop_check else 15),
                 'macros':['sector_a','sector_b'],'roles':{}}
        try:
            if drop_check or duplicate_ready or fail_inspect:
                with self.assertRaises((TimeoutError,RuntimeError,ValueError)):participant.on_ready(context)
                if not fail_inspect:self.assertFalse(any(op=='START' for _,op in order))
                self.assertFalse(any(op=='ACK' for _,op in order))
            else:
                result=participant.on_ready(context)
                self.assertTrue(result['tcp_ack_after_client_inspect'])
                self.assertLess(order.index(('client','DESCRIPTOR')),order.index(('server','ACK')))
                self.assertTrue(participant.cleanup_before_owned_processes())
                self.assertTrue(all(h.proc.returncode==0 and h.pidfd is None for h in participant.helpers))
                def logs(items):return ''.join('[X4LAN] AUTH_PAIR_CREATE '+x+'\n' for x in items).encode()
                evidence={'server':logs(['READY','CHECKED','DESCRIPTOR','CHECKED','FINISHED']),
                          'client':logs(['READY','AWAIT','CHECKED','INSPECTED'])}
                self.assertTrue(participant.verify_final(evidence))
                evidence['client']+=logs(['ERROR FAULT'])
                self.assertFalse(participant.verify_final(evidence))
        finally:
            stop.set()
            participant.cleanup_before_owned_processes();participant.cleanup_after_owned_processes()
            for thread in threads:thread.join(2)
        self.assertEqual(errors,[])

    def test_full_fake_transfer_and_helper(self):self.run_fake()
    def test_guard_failure_before_mutation(self):self.run_fake(drop_check=True)
    def test_duplicate_ready_fails_before_mutation(self):self.run_fake(duplicate_ready=True)
    def test_process_guard_loss_after_client_create_prevents_ack(self):self.run_fake(fail_inspect=True)

    def test_final_datagram_and_log_fault_are_rejected(self):
        participant=m.PairTransferParticipant();peers=[]
        try:
            for role in ('server','client'):
                sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.setblocking(False)
                peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peers.append(peer)
                participant.roles[role]={'sock':sock};participant.sockets.append(sock)
            participant.complete=True
            def log(labels):return ''.join('[X4LAN] AUTH_PAIR_CREATE '+s+'\n' for s in labels).encode()
            logs={'server':log(['READY','DESCRIPTOR','FINISHED']), 'client':log(['READY','AWAIT','INSPECTED'])}
            self.assertTrue(participant.verify_final(logs))
            self.assertFalse(participant.check_live_log('client',log(['ERROR FAULT'])))
            peers[0].sendto(b'duplicate',participant.roles['server']['sock'].getsockname())
            self.assertFalse(participant.verify_final(logs))
        finally:
            for peer in peers:peer.close()
            participant.cleanup_before_owned_processes();participant.cleanup_after_owned_processes()

if __name__=='__main__':unittest.main()
