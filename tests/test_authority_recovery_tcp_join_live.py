"""Focused offline checks; these tests do not start X4."""
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_recovery_tcp_join_live as subject


class RecoveryJoinTest(unittest.TestCase):
    def test_output_must_be_disjoint_and_source_is_fixed(self):
        origin = subject.source.DEFAULT_STORE.parent
        with self.assertRaises(ValueError): subject.check_separate(origin/'nested', subject.source.DEFAULT_STORE)
        with self.assertRaises(ValueError): subject.check_separate(origin.parent, subject.source.DEFAULT_STORE)
        with self.assertRaises(ValueError): subject.check_separate(origin.parent/'another', origin)

    def test_client_receipts_exact_order_and_fixture_presence(self):
        ticket = dict(world_epoch='epoch', connection_handle=1, baseline_id=1, load_generation=1,
            checkpoint_id='checkpoint-'+'a'*32, sha256='b'*64, attempt_id='c'*32, slot='save_009')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'client.log'; marker='d'*32
            watch = subject.base.client.ReceiptWatch(path,ticket)
            identity = (b'[X4LAN] AUTH_IDENTITY load ACTOR 1 id=123 name=Authority identity alpha 7181 macro=ship_arg_s_fighter_01_a_macro\n'
                        b'[X4LAN] AUTH_IDENTITY load ACTOR 2 id=456 name=Authority identity beta 7182 macro=ship_arg_s_fighter_01_a_macro\n'
                        b'[X4LAN] AUTH_IDENTITY load READY\n')
            request=subject.base.client.TAG+watch.expected[0]+b'\n'
            inspected=b'AUTH_MARKER load INSPECTED '+marker.encode()+b'\n'
            paused=subject.base.client.TAG+watch.expected[1]+b'\n'
            content = request+inspected+identity+paused
            path.write_bytes(content); subject.check_client_log(path,ticket,marker)
            for bad in (content[:-1], content+subject.base.client.TAG+watch.expected[1]+b'\n',
                        content.replace(marker.encode(),b'e'*32),content.replace(identity,b''),
                        identity+request+inspected+paused,request+inspected+paused+identity):
                path.write_bytes(bad)
                with self.assertRaises(ValueError): subject.check_client_log(path,ticket,marker)

    def test_server_command_includes_all_protected_files_and_save(self):
        participant = subject.RecoveredParticipant(time.monotonic()+20, subject.source.DEFAULT_STORE)
        try:
            case=Path('/private/case'); participant.server_case=case
            participant.target=Path('/private/save'); participant.server_expected={Path('/private/config'):'x',Path('/private/md'):'y'}
            participant.check_server_files=lambda: True
            with patch.object(subject.load,'readonly_save_command',return_value=['bwrap','--die-with-parent']) as command:
                result=participant.recovery_server_command(case,'game','bind','lock','display','auth','user',42)
            self.assertEqual(command.call_args.args[-1],participant.target)
            self.assertEqual(result,['bwrap','--ro-bind','/private/config','/private/config',
                '--ro-bind','/private/md','/private/md','--die-with-parent'])
            with self.assertRaises(ValueError):
                participant.recovery_server_command(Path('/foreign'),'game','bind','lock','display','auth','user',42)
        finally: participant.close()

    def test_enrollment_requires_living_identity_and_stable_files(self):
        participant = subject.RecoveredParticipant(time.monotonic()+20, subject.source.DEFAULT_STORE)
        participant.checkpoint=SimpleNamespace(marker='a'*32)
        try:
            def activate(sock,watch,lease,epoch,deadline,check,verify):
                watch.stage=3; check(); verify(); return ('127.0.0.1',1234)
            kwargs=dict(sock=object(),lease='b'*32,epoch='c'*32,deadline=time.monotonic()+10,
                server_proc=object(),server_started=1,game=Path('/game'),steam='steam',home=Path('/home/u'),
                uid=1,profile=Path('/private'))
            with patch.object(subject.recovery_bridge,'activate',side_effect=activate), \
                 patch.object(subject.base.client,'game_identity',return_value=(123,456)), \
                 patch.object(subject.live,'steam_identity',return_value='steam'), \
                 patch.object(participant,'check_server_files',return_value=True):
                peer, identity=participant.enroll_recovered_server(**kwargs)
            self.assertEqual((peer,identity),(('127.0.0.1',1234),(123,456)))
            with patch.object(subject.recovery_bridge,'activate',side_effect=activate), \
                 patch.object(subject.base.client,'game_identity',return_value=None), \
                 patch.object(subject.live,'steam_identity',return_value='steam'):
                with self.assertRaises(RuntimeError): participant.enroll_recovered_server(**kwargs)
        finally: participant.close()

    def test_server_files_changed_or_missing_are_rejected(self):
        participant = subject.RecoveredParticipant(time.monotonic()+20, subject.source.DEFAULT_STORE)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                target=Path(tmp)/'save'; config=Path(tmp)/'config'
                target.write_bytes(b'save'); config.write_bytes(b'config')
                participant.target=target
                participant.checkpoint=SimpleNamespace(sha256=subject.live.sha(target))
                participant.server_expected={config:subject.live.sha(config)}
                self.assertTrue(participant.check_server_files())
                config.write_bytes(b'changed')
                with self.assertRaises(ValueError): participant.check_server_files()
                result={'success': True}
                subject.base.check_final_recovery_files(result, participant)
                self.assertFalse(result['success'])
                self.assertIn('final recovery state invalid', result['error'])
        finally: participant.close()

    def test_join_checkpoint_and_marker_must_be_fresh(self):
        participant=subject.RecoveredParticipant(time.monotonic()+20, subject.source.DEFAULT_STORE)
        participant.checkpoint=SimpleNamespace(checkpoint_id='old',marker='old-marker')
        try:
            with patch.object(subject.tcp.TCPMarkedParticipant, 'offer_and_download',
                              return_value=({'checkpoint_id':'new'}, Path('/save'))):
                participant.marker='new-marker'
                self.assertEqual(participant.offer_and_download(None,None,1,None,None)[0]['checkpoint_id'],'new')
                participant.marker='old-marker'
                with self.assertRaises(ValueError): participant.offer_and_download(None,None,1,None,None)
            with patch.object(subject.tcp.TCPMarkedParticipant, 'offer_and_download',
                              return_value=({'checkpoint_id':'old'}, Path('/save'))):
                participant.marker='new-marker'
                with self.assertRaises(ValueError): participant.offer_and_download(None,None,1,None,None)
        finally: participant.close()

if __name__ == '__main__': unittest.main()
