"""Offline checks for the isolated recovery handoff; no X4 process."""
import importlib.util
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

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
