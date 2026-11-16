"""Offline checks for the isolated recovery handoff; no X4 process."""
import importlib.util
import os
from contextlib import ExitStack
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_recovery_bridge_live as subject

LEASE='a'*32; EPOCH='b'*32; PEER=('127.0.0.1',4321)
class Watch:
    stage=3
    def poll(self): return True
class Sock:
    def __init__(self, events): self.events=list(events); self.sent=[]
    def recvfrom(self,_):
        if not self.events: raise socket.timeout()
        return self.events.pop(0)
    def sendto(self,data,peer): self.sent.append((data,peer)); return len(data)
def msg(kind): return f'{kind}|{LEASE}|{EPOCH}'.encode()

class RecoveryBridgeTests(unittest.TestCase):
    def test_activation_only_after_ordered_evidence_and_verification(self):
        sock=Sock([(msg('RECOVERY_READY'),PEER),(msg('RECOVERY_READY'),PEER),(msg('ACTIVATED'),PEER)])
        checks=[]
        result=subject.activate(sock,Watch(),LEASE,EPOCH,time.monotonic()+2,
            lambda:checks.append('check'), lambda:checks.append('verify'))
        self.assertEqual(result,PEER); self.assertEqual(sock.sent,[(msg('ACTIVATE'),PEER)])
        self.assertEqual(checks.count('verify'),2)

    def test_incomplete_mismatched_or_dead_context_never_activates(self):
        class Incomplete(Watch): stage=2
        for watch,event,verify in ((Watch(),b'WRONG',lambda:None),
                                    (Watch(),msg('RECOVERY_READY'),lambda:(_ for _ in ()).throw(ValueError('changed')))):
            sock=Sock([(event,PEER)])
            with self.assertRaises(ValueError):
                subject.activate(sock,watch,LEASE,EPOCH,time.monotonic()+1,lambda:None,verify)
            self.assertEqual(sock.sent,[])
        sock=Sock([(msg('RECOVERY_READY'),PEER)])
        with self.assertRaises(TimeoutError):
            subject.activate(sock,Incomplete(),LEASE,EPOCH,time.monotonic()+.001,lambda:None,lambda:None)
        self.assertEqual(sock.sent,[])
        sock=Sock([(msg('RECOVERY_READY'),PEER)])
        with self.assertRaises(RuntimeError):
            subject.activate(sock,Watch(),LEASE,EPOCH,time.monotonic()+1,
                lambda:(_ for _ in ()).throw(RuntimeError('process died')),lambda:None)
        self.assertEqual(sock.sent,[])

    def test_ack_must_come_from_same_peer_and_no_duplicate_receipts(self):
        sock=Sock([(msg('RECOVERY_READY'),PEER),(msg('ACTIVATED'),('127.0.0.1',4322))])
        with self.assertRaises(ValueError):
            subject.activate(sock,Watch(),LEASE,EPOCH,time.monotonic()+1,lambda:None,lambda:None)
        self.assertEqual(sock.sent,[(msg('ACTIVATE'),PEER)])
        class Changed(Watch):
            def __init__(self): self.calls=0
            def poll(self): self.calls+=1; return self.calls<4
        sock=Sock([(msg('RECOVERY_READY'),PEER),(msg('ACTIVATED'),PEER)])
        with self.assertRaises(ValueError):
            subject.activate(sock,Changed(),LEASE,EPOCH,time.monotonic()+1,lambda:None,lambda:None)

    def test_ready_retries_until_log_catches_up(self):
        class Delayed(Watch):
            def __init__(self): self.stage=2; self.calls=0
            def poll(self):
                self.calls+=1
                if self.calls>=3: self.stage=3
                return True
        sock=Sock([(msg('RECOVERY_READY'),PEER),(msg('RECOVERY_READY'),PEER),(msg('ACTIVATED'),PEER)])
        self.assertEqual(subject.activate(sock,Delayed(),LEASE,EPOCH,time.monotonic()+1,
            lambda:None,lambda:None),PEER)
        self.assertEqual(sock.sent,[(msg('ACTIVATE'),PEER)])

    def test_lock_is_recorded_before_deferred_signal_is_raised(self):
        handlers={}; box=[]; registry={}
        def change(number,handler):
            old=registry.get(number,'old'); registry[number]=handler; return old
        def acquire(*_):
            registry[subject.signal.SIGTERM](subject.signal.SIGTERM,None)
            return (17,'owned')
        with patch.object(subject.signal,'signal',side_effect=change), patch.object(subject.live,'create_lock_target',side_effect=acquire):
            with self.assertRaises(InterruptedError):
                subject.acquire_lock_with_handlers(handlers,box,123,456)
        self.assertEqual(box,[(17,'owned')]); self.assertEqual(len(handlers),3)

    def test_lock_creation_failure_keeps_previous_handler_ownership(self):
        handlers={};box=[]
        with patch.object(subject.signal,'signal',return_value='old'), patch.object(subject.live,'create_lock_target',side_effect=OSError('lock')):
            with self.assertRaises(OSError): subject.acquire_lock_with_handlers(handlers,box,123,456)
        self.assertEqual(box,[]);self.assertEqual(len(handlers),3)

    def test_cleanup_retains_config_and_lock_without_confirmed_process_stop(self):
        for mode in ('no_process','stopped','survives','raises','invalid','unknown_identity'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                root=Path(d);out=root/'output';game=root/'game';(game/'extensions').mkdir(parents=True)
                (game/'X4').touch();auth=root/'auth';auth.touch();source=root/'source';source.write_bytes(b'save')
                store_dir=root/'source-store/checkpoints';store_dir.mkdir(parents=True);lock=root/'lock'
                config=out/'case/extensions/x4_lan_lab/ui/config.lua'
                original='authority_control_lease="'+LEASE+'"\n'
                checkpoint=SimpleNamespace(marker='c'*32,sha256='expected')
                args=SimpleNamespace(out=out,store=store_dir,game=game,display=':0',timeout=300,seed=1)
                user=SimpleNamespace(pw_dir=str(root),pw_uid=1000,pw_gid=1000,pw_name='tester')
                proc=Mock(pid=123);proc.poll.return_value=None
                with ExitStack() as stack:
                    def replace(obj,name,value): return stack.enter_context(patch.object(obj,name,value))
                    stack.enter_context(patch.dict(os.environ,{'XAUTHORITY':str(auth)}))
                    replace(subject.os,'geteuid',lambda:1000)
                    replace(subject.snapshot,'output_path',lambda _:out)
                    replace(subject.snapshot,'LOCK_TARGET',lock)
                    replace(subject.load,'local_directory',lambda p:p)
                    replace(subject,'CheckpointStore',lambda path:SimpleNamespace(directory=Path(path)))
                    replace(subject.live,'sha',lambda _: 'expected')
                    replace(subject.live,'EXE_SHA','expected')
                    replace(subject.live,'x4_executables',lambda:[])
                    replace(subject.shutil,'which',lambda _: '/bin/bwrap')
                    replace(subject.pwd,'getpwuid',lambda _:user)
                    replace(subject.live,'steam_identity',lambda *_:('stable',))
                    def prepare(*_):
                        case=out/'case';profile=case/'profile';(profile/'save').mkdir(parents=True)
                        return case,profile,[],lock
                    replace(subject.snapshot,'prepare_case',prepare)
                    replace(subject,'stage_confirmed_recovery',lambda *_:(checkpoint,source))
                    replace(subject,'verify_selected_source',lambda *_:None)
                    def install(*_):
                        config.parent.mkdir(parents=True);config.write_text(original)
                        return [config]
                    replace(subject,'install_probe',install)
                    def acquire(_handlers,lockbox,*_):
                        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
                        lockbox.append((fd,os.fstat(fd)))
                    replace(subject,'acquire_lock_with_handlers',acquire)
                    def release(path,fd,info):
                        self.assertEqual((path.stat().st_dev,path.stat().st_ino),(info.st_dev,info.st_ino))
                        path.unlink();os.close(fd)
                    release_mock=replace(subject.live,'release_lock_target',Mock(side_effect=release))
                    replace(subject.load,'readonly_save_command',lambda *_:['bwrap','--die-with-parent'])
                    def spawn(_command,_log,processes):
                        if mode!='no_process': processes.append([proc,None if mode=='unknown_identity' else 7])
                        raise RuntimeError('end diagnostic')
                    replace(subject.owned,'spawn_owned_gated',spawn)
                    replace(subject.snapshot,'stop_owned',Mock(side_effect=OSError('stop')) if mode=='raises' else
                            Mock(return_value=[99] if mode=='survives' else (None if mode=='invalid' else [])))
                    result=subject.run(args)
                self.assertFalse(result['success'])
                if mode in ('no_process','stopped'):
                    self.assertEqual(result['owned_processes_remaining'],[])
                    release_mock.assert_called_once();self.assertFalse(lock.exists())
                    self.assertEqual(config.read_text(),'authority_control_lease="redacted"\n')
                else:
                    self.assertEqual(result['owned_processes_remaining'],[99] if mode=='survives' else None)
                    release_mock.assert_not_called();self.assertTrue(lock.exists())
                    self.assertEqual(config.read_text(),original)
                    self.assertIn('lock retained: owned process stop unconfirmed',result['cleanup_errors'])
                    self.assertIn('lease cleanup: RuntimeError',result['cleanup_errors'])

    def test_private_probe_has_explicit_gate_and_no_conflicting_stored_handler(self):
        with tempfile.TemporaryDirectory() as d:
            case=Path(d)/'case'; profile=case/'home/.config/EgoSoft/X4/45841'
            profile.mkdir(parents=True);(profile/'content.xml').write_text('');(profile/'config.xml').write_text('')
            def fake_install(case,port,lease,epoch,marker_required):
                self.assertTrue(marker_required)
                lab=case/'extensions/x4_lan_lab';ui=lab/'ui'
                ui.mkdir(parents=True);(lab/'md').mkdir();(lab/'native').mkdir()
                (lab/'native/x4lan_net.so').write_bytes(b'')
                (lab/'md/authority_checkpoint_marker.xml').write_bytes(b'')
                for name in ('authority_control_state.lua','x4_control_engine.lua','local_control_bridge.lua'):
                    (ui/name).write_text('')
                shutil.copyfile(ROOT/'tools/dev/authority_world_bridge_probe.lua',ui/'authority_world_bridge_probe.lua')
            with patch.object(subject.bridge_install,'install_probe',fake_install):
                subject.install_probe(case,profile,1234,LEASE,EPOCH)
            ui=case/'extensions/x4_lan_lab/ui'
            marker=(ui/'authority_checkpoint_marker_probe.lua').read_text()
            bridge=(ui/'authority_world_bridge_probe.lua').read_text()
            recover=(ui/'authority_recovery_probe.lua').read_text()
            self.assertNotIn("RegisterEvent('X4AuthorityCheckpointMarker.Stored'",marker)
            self.assertIn("RegisterEvent('X4AuthorityCheckpointMarker.Stored'",bridge)
            self.assertLess(bridge.index('if not X4LAN_AUTHORITY_RECOVERY_READY()'),bridge.index('if not activated then'))
            self.assertLess(bridge.index('if not activated then'),bridge.index('if not bridge then'))
            self.assertIn("assert(C.IsGamePaused()",bridge)
            self.assertIn("net:send('RECOVERY_READY|'",bridge)
            self.assertIn("net:send('ACTIVATED|'",bridge)
            self.assertNotIn("net:send('HELLO|'",bridge)
            self.assertIn("return state=='done' and not failed",recover)
            if shutil.which('luajit'):
                for f in ('authority_checkpoint_marker_probe.lua','authority_recovery_probe.lua','authority_world_bridge_probe.lua'):
                    subprocess.run(['luajit','-b',str(ui/f),str(Path(d)/(f+'.out'))],check=True,capture_output=True)
                subprocess.run(['luajit',str(ROOT/'tests/authority_recovery_bridge_probe.lua'),
                    str(ui/'authority_world_bridge_probe.lua')],check=True,capture_output=True)
                subprocess.run(['luajit',str(ROOT/'tests/authority_recovery_bridge_combined.lua'),
                    str(ui/'authority_recovery_probe.lua'),str(ui/'authority_world_bridge_probe.lua')],
                    check=True,capture_output=True)

if __name__=='__main__': unittest.main()
