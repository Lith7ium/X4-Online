"""Synthetic tests and local UDP only; no X4 launch."""
import importlib.util
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('job_single_live',ROOT/'tools/dev/authority_job_registry_single_live.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class SingleJobTest(unittest.TestCase):
    def test_partial_setup_redacts_existing_lease_and_closes_sockets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);game=root/'game';game.mkdir();(game/'X4').write_bytes(b'fake');(game/'extensions').mkdir()
            auth=root/'xauth';auth.write_text('fake');out=root/'out';lease='a'*32
            class FakeSock:
                def __init__(self): self.closed=False
                def bind(self,_): pass
                def settimeout(self,_): pass
                def getsockname(self): return ('127.0.0.1',1101)
                def close(self): self.closed=True
            one,two=FakeSock(),FakeSock()
            def prepare(target,*_):
                case=target/'case';profile=case/'home/.config/EgoSoft/X4/45841'
                (profile/'save').mkdir(parents=True);(case/'extensions/x4_lan_lab/ui').mkdir(parents=True)
                return case,profile,[],case/'lock'
            def fail_install(case,profile,**kw):
                (case/'extensions/x4_lan_lab/ui/config.lua').write_text(f'authority_control_lease="{kw["bridge_lease"]}"\n')
                raise OSError('injected overlay failure')
            args=types.SimpleNamespace(game=game,out=out,display=':9',timeout=100.,window=5.,seed=1)
            with patch.dict(module.os.environ,{'XAUTHORITY':str(auth)}), \
                 patch.object(module.snapshot,'output_path',return_value=out), \
                 patch.object(module.snapshot,'prepare_case',side_effect=prepare), \
                 patch.object(module.live,'sha',return_value=module.live.EXE_SHA), \
                 patch.object(module.live,'x4_executables',return_value=[]), \
                 patch.object(module.live,'steam_identity',return_value='steam'), \
                 patch.object(module.shutil,'which',return_value='/fake/bwrap'), \
                 patch.object(module.secrets,'token_hex',side_effect=[lease,'b'*32,'c'*32]), \
                 patch.object(module.socket,'socket',side_effect=[one,two]), \
                 patch.object(module.subprocess,'Popen') as popen, \
                 patch.object(module,'install',side_effect=fail_install):
                result=module.run(args)
            self.assertFalse(result['success']);self.assertFalse(result['lifecycle_success'])
            self.assertFalse(result['event_observed']);self.assertIn('injected overlay failure',result['error'])
            popen.assert_not_called();self.assertTrue(one.closed and two.closed)
            self.assertNotIn(lease,(out/'case/extensions/x4_lan_lab/ui/config.lua').read_text())

    def test_mocked_run_confirms_pause_and_cleans_owned_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);game=root/'game';game.mkdir();(game/'X4').write_bytes(b'fake');(game/'extensions').mkdir()
            auth=root/'xauth';auth.write_text('fake');out=root/'out';calls=[]
            lease,epoch,job_lease='a'*32,'b'*32,'c'*32
            class FakeSock:
                def __init__(self,kind): self.kind=kind;self.closed=False;self.q=[]
                def bind(self,_): pass
                def settimeout(self,_): pass
                def getsockname(self): return ('127.0.0.1',1101 if self.kind=='bridge' else 1102)
                def recvfrom(self,_):
                    if self.q: return self.q.pop(0),('127.0.0.1',1201 if self.kind=='bridge' else 1202)
                    raise socket.timeout()
                def sendto(self,data,_):
                    calls.append('start')
                    self.q.extend([f'JOB|{job_lease}|{epoch}|STARTED'.encode(),
                                   f'JOB|{job_lease}|{epoch}|DONE|0|0|0|inconclusive_no_events'.encode()])
                def close(self): self.closed=True
            bridge_sock,job_sock=FakeSock('bridge'),FakeSock('job')
            bridge_sock.q.append(f'HELLO|{lease}|{epoch}'.encode())
            job_sock.q.append(f'JOB|{job_lease}|{epoch}|HELLO'.encode())
            class FakeProc:
                pid=42
                def poll(self): return None
            class Bridge:
                def __init__(self,**kw): self._timeout=kw['timeout']
                def pause(self): calls.append('pause')
                def resume(self): calls.append('resume')
            def prepare(target,*_):
                case=target/'case';profile=case/'home/.config/EgoSoft/X4/45841'
                (profile/'save').mkdir(parents=True);(case/'extensions/x4_lan_lab/ui').mkdir(parents=True)
                return case,profile,[],case/'lock'
            def install(case,profile,**kw):
                (case/'extensions/x4_lan_lab/ui/config.lua').write_text(
                    f'authority_control_lease="{kw["bridge_lease"]}"\nauthority_job_lease="{kw["job_lease"]}"\n')
            args=types.SimpleNamespace(game=game,out=out,display=':9',timeout=100.,window=5.,seed=1)
            with patch.dict(module.os.environ,{'XAUTHORITY':str(auth)}), \
                 patch.object(module.snapshot,'output_path',return_value=out), \
                 patch.object(module.snapshot,'prepare_case',side_effect=prepare), \
                 patch.object(module.snapshot,'command_for',return_value=['fake']), \
                 patch.object(module.snapshot,'stop_owned',side_effect=lambda *_:calls.append('cleanup') or []), \
                 patch.object(module.live,'sha',return_value=module.live.EXE_SHA), \
                 patch.object(module.live,'x4_executables',return_value=[]), \
                 patch.object(module.live,'steam_identity',return_value='steam'), \
                 patch.object(module.live,'create_lock_target',return_value=(9,'lock')), \
                 patch.object(module.live,'release_lock_target'), \
                 patch.object(module.live,'start_ticks',return_value=1), \
                 patch.object(module.process_utils,'game_identity',return_value=(99,1)), \
                 patch.object(module.shutil,'which',return_value='/fake/bwrap'), \
                 patch.object(module.secrets,'token_hex',side_effect=[lease,epoch,job_lease]), \
                 patch.object(module.socket,'socket',side_effect=[bridge_sock,job_sock]), \
                 patch.object(module.subprocess,'Popen',return_value=FakeProc()), \
                 patch.object(module,'LocalControlBridge',Bridge), \
                 patch.object(module,'install',side_effect=install):
                result=module.run(args)
            self.assertTrue(result['success'],result)
            self.assertTrue(result['lifecycle_success'])
            self.assertFalse(result['event_observed']);self.assertFalse(result['event_coverage_proven'])
            self.assertEqual(result['observation']['classification'],'inconclusive_no_events')
            self.assertEqual(result['observation']['events'],[])
            self.assertEqual(calls,['pause','resume','start','pause','cleanup'])
            self.assertTrue(bridge_sock.closed and job_sock.closed)
            self.assertNotIn('save_created',result['observation'])
            self.assertFalse(result['observation']['checkpoint_requested'])
            config=(out/'case/extensions/x4_lan_lab/ui/config.lua').read_text()
            self.assertNotIn(lease,config);self.assertNotIn(job_lease,config)

    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_lua_one_shot_and_empty_baseline(self):
        subprocess.run(['luajit','tests/authority_job_registry_single_probe.lua'],cwd=ROOT,
                       check=True,capture_output=True,text=True,timeout=5)

    def test_install_preserves_single_bridge_update_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';lab=case/'extensions/x4_lan_lab';profile=case/'home/.config/EgoSoft/X4/45841'
            (lab/'ui').mkdir(parents=True);(lab/'md').mkdir();(profile/'save').mkdir(parents=True)
            def install_world(*_args,**_kwargs):
                (lab/'ui/config.lua').write_text('X4LAN_CONFIG = {authority_control_lease="'+'a'*32+'"}\n')
                (lab/'ui.xml').write_text('    <file name="ui/authority_world_bridge_probe.lua" />\n')
                (lab/'ui/authority_world_bridge_probe.lua').write_text(' local ok,reason=bridge:update();assert(ok,reason)\n')
            with patch.object(module.world_bridge,'install_probe',side_effect=install_world):
                module.install(case,profile,bridge_port=1001,bridge_lease='a'*32,epoch='b'*32,
                               job_port=1002,job_lease='c'*32,window=10,request_timeout=5,capacity=8)
            config=(lab/'ui/config.lua').read_text();bridge=(lab/'ui/authority_world_bridge_probe.lua').read_text()
            self.assertIn('authority_job_single=true',config)
            self.assertIn('assert(X4LAN_JOB_REGISTRY_SINGLE_TICK)()',bridge)
            self.assertNotIn('SetScript(', (lab/'ui/authority_job_registry_single_probe.lua').read_text().replace('-- update; this file must never install its own SetScript or start the game.',''))
            self.assertTrue((lab/'md/authority_job_ship_events.xml').is_file())
            self.assertEqual((lab/'ui/config.lua').stat().st_mode & 0o777,0o600)

    def test_channel_binds_peer_and_one_shot_framing_over_udp(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as peer:
            client.bind(('127.0.0.1',0));peer.bind(('127.0.0.1',0));peer.settimeout(2)
            lease,epoch='a'*32,'b'*32
            def game():
                raw,addr=peer.recvfrom(1024)
                assert raw.decode()==f'JOBSTART|{lease}|{epoch}'
                for row in ('HELLO','STARTED','EVENT|1|1|new_registry_entry','DONE|1|1|0|local_activations_observed'):
                    peer.sendto(f'JOB|{lease}|{epoch}|{row}'.encode(),addr)
            thread=threading.Thread(target=game,daemon=True);thread.start()
            channel=module.JobChannel(client,peer.getsockname(),lease,epoch,time.monotonic()+3,start_timeout=1)
            channel.start();kind,event=channel.receive(1);end_kind,end=channel.receive(1)
            thread.join(2);self.assertFalse(thread.is_alive())
            self.assertEqual((kind,event['sequence'],event['index']),('event',1,1))
            self.assertEqual((end_kind,end['observed'],end['baseline_count']),('done',1,0))
            with self.assertRaisesRegex(RuntimeError,'one-shot'): channel.start()

    def test_lost_start_does_not_reissue_or_start(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as peer:
            client.bind(('127.0.0.1',0));peer.bind(('127.0.0.1',0));peer.settimeout(.2)
            channel=module.JobChannel(client,peer.getsockname(),'a'*32,'b'*32,time.monotonic()+2,start_timeout=.1)
            with self.assertRaises(TimeoutError): channel.start()
            first,_=peer.recvfrom(1024);self.assertTrue(first.startswith(b'JOBSTART|'))
            with self.assertRaises(RuntimeError): channel.start()
            with self.assertRaises(socket.timeout): peer.recvfrom(1024)

    def test_nonempty_done_baseline_is_rejected(self):
        channel=module.JobChannel(None,('127.0.0.1',1234),'a'*32,'b'*32,time.monotonic()+2)
        channel.started=True
        with patch.object(channel,'_receive',return_value=['DONE','0','0','1','inconclusive_no_events']):
            with self.assertRaisesRegex(ValueError,'malformed or unexpected'):
                channel.receive(1)

if __name__=='__main__': unittest.main()
