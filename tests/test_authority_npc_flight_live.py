"""Offline wiring checks for the opt-in diagnostic; no X4 starts."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import shutil
import subprocess
import socket
import types
from unittest.mock import patch
from tests.test_authority_npc_flight_evidence import inputs

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('npc_flight_live_test',ROOT/'tools/dev/authority_npc_flight_live.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class InstallTest(unittest.TestCase):
    def test_one_repeating_peer_does_not_extend_create_handshake(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);experiment=module.FlightExperiment(flight_seconds=5,bridge_timeout=1)
            experiment.sock.close();experiment.flight_sock.close();experiment.relay.close()
            class OnlyServer:
                def recvfrom(self,_): return f'RESULT|{experiment.lease}|server|HELLO'.encode(),('127.0.0.1',1)
                def close(self): pass
            class Relay:
                def poll(self,*_): pass
                def close(self): pass
            class Clock:
                now=0.
                def monotonic(self): self.now+=.1;return self.now
            class Dummy:
                def close(self): pass
            experiment.sock=OnlyServer();experiment.flight_sock=Dummy();experiment.relay=Relay()
            world=types.SimpleNamespace(session=types.SimpleNamespace(state='paused',pending=None,ready_players=()))
            offers=types.SimpleNamespace(service=Dummy())
            experiment.bind_world(world,Dummy(),offers);clock=Clock()
            try:
                with patch.object(module.time,'monotonic',side_effect=clock.monotonic), \
                     patch.object(module.base.client,'game_identity',side_effect=lambda proc,*_:proc), \
                     patch.object(module.base.live,'steam_identity',return_value='initial-steam'):
                    with self.assertRaisesRegex(TimeoutError,'HELLO'):
                        experiment.on_ready(world=world,server_proc='server',server_started=1,server_identity='server',
                            client_proc='client',client_started=2,client_identity='client',game=root,out=root,
                            deadline=900,result={},steam_identity='initial-steam')
            finally: experiment.close()
            self.assertLess(clock.now,32)

    @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'),'C compiler and LuaJIT required')
    def test_async_md_callback_sends_armed_over_real_loopback_udp(self):
        with tempfile.TemporaryDirectory() as temp, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as peer:
            peer.bind(('127.0.0.1',0));peer.settimeout(3)
            fake=Path(temp)/'fake-x4.so';network=Path(temp)/'net.so'
            for source,target in (('tests/lua/authority_npc_source_fake_x4.c',fake),('src/native/net.c',network)):
                subprocess.run(['cc','-shared','-fPIC',source,'-o',str(target),'-ldl'],
                               cwd=ROOT,check=True,capture_output=True,text=True,timeout=10)
            lease='b'*32
            process=subprocess.Popen(['luajit','tests/lua/authority_npc_async_udp_probe.lua',str(fake),str(network),
                                      str(peer.getsockname()[1]),lease],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                data,address=peer.recvfrom(1024)
                self.assertEqual(data.decode(),f'NPCRESULT|{lease}|HELLO')
                peer.sendto(f'NPCCMD|{lease}|ARM|sectorA'.encode(),address)
                deadline=module.time.monotonic()+3
                while True:
                    self.assertLess(module.time.monotonic(),deadline)
                    data,sender=peer.recvfrom(1024)
                    self.assertEqual(sender,address)
                    if data.decode()==f'NPCRESULT|{lease}|ARMED|sectorA': break
                    self.assertEqual(data.decode(),f'NPCRESULT|{lease}|HELLO')
                # Simulate losing the first ARMED datagram. UDP send success is
                # not delivery, so the paused source must advertise it again.
                while True:
                    self.assertLess(module.time.monotonic(),deadline)
                    data,sender=peer.recvfrom(1024)
                    self.assertEqual(sender,address)
                    if data.decode()==f'NPCRESULT|{lease}|ARMED|sectorA': break
                    self.assertEqual(data.decode(),f'NPCRESULT|{lease}|HELLO')
                stdout,stderr=process.communicate(timeout=5)
                self.assertEqual(process.returncode,0,stdout+stderr)
                self.assertIn('AUTH_NPC_SOURCE ORDER',stdout)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_simulated_runner_fences_offer_and_confirms_pause(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);experiment=module.FlightExperiment(flight_seconds=5,bridge_timeout=1)
            experiment.sock.close();experiment.flight_sock.close();experiment.relay.close()
            records=inputs();records['guest_actor']='84'
            for row in records['guest_writes']+records['guest_readbacks']: row['actor']='84'
            experiment.epoch=records['epoch'];sector=records['frame'];calls=[]
            def line(prefix,row): return prefix+' '.join(str(k)+'='+str(v) for k,v in row.items())+'\n'
            server=line('AUTH_NPC_SOURCE ORDER ',records['order'])+''.join(line('AUTH_NPC_SOURCE SAMPLE ',r) for r in records['source'])
            guest=''.join(line('NATURAL_GUEST_WRITE ',r) for r in records['guest_writes'])+''.join(line('NATURAL_GUEST_OBSERVE ',r) for r in records['guest_readbacks'])
            for role,text in (('server',server),('client',guest)):
                log=root/role/'case/home/.config/EgoSoft/X4/45841/engine-output.log'
                log.parent.mkdir(parents=True);log.write_text(text)
            class Relay:
                fixture=None
                def poll(self,*_): pass
                def close(self): pass
            class FlightSocket:
                def __init__(self): self.q=[(f'NPCRESULT|{experiment.flight_lease}|HELLO'.encode(),('127.0.0.1',3))]
                def sendto(self,data,addr):
                    op=data.decode().split('|')[2]
                    if op=='ARM': self.q.append((f'NPCRESULT|{experiment.flight_lease}|ARMED|{sector}'.encode(),addr))
                    elif op=='STOP': self.q.append((f'NPCRESULT|{experiment.flight_lease}|STOPPED'.encode(),addr))
                def recvfrom(self,_):
                    if not self.q: raise socket.timeout()
                    return self.q.pop(0)
                def close(self): pass
            class ControlSocket:
                def __init__(self):
                    self.address={'server':('127.0.0.1',1),'client':('127.0.0.1',2)}
                    self.q=[(f'RESULT|{experiment.lease}|{role}|HELLO'.encode(),addr) for role,addr in self.address.items()]
                def sendto(self,data,addr):
                    op=data.decode().split('|')[2];role=next(k for k,v in self.address.items() if v==addr)
                    payload={'SPAWN':f'SPAWN|1|42|5|6|{sector}|ship_arg_s_fighter_01_a_macro|argon|7183|-400|100000|500',
                             'CREATE':f'CREATE|1|84|7|8|{sector}','REPLAY':f'REPLAY|1|84|7|8|{sector}',
                             'MOTION':'MOTION','MOTIONSTOP':'MOTIONSTOP'}[op]
                    self.q.append((f'RESULT|{experiment.lease}|{role}|{payload}'.encode(),addr))
                def recvfrom(self,_):
                    if not self.q: raise socket.timeout()
                    return self.q.pop(0)
                def close(self): pass
            experiment.sock=ControlSocket();experiment.flight_sock=FlightSocket();experiment.relay=Relay()
            class Engine:
                def resume(self):
                    calls.append('resume')
                    # A retry may already be queued when the bridge resumes.
                    experiment.flight_sock.q.append((f'NPCRESULT|{experiment.flight_lease}|ARMED|{sector}'.encode(),('127.0.0.1',3)))
                    experiment.flight_sock.q.append((f'NPCRESULT|{experiment.flight_lease}|RUNNING'.encode(),('127.0.0.1',3)))
                def pause(self): calls.append('pause')
            service=types.SimpleNamespace(close=lambda:calls.append('close'))
            offers=types.SimpleNamespace(service=service,invalidate=lambda:calls.append('invalidate'))
            world=types.SimpleNamespace(session=types.SimpleNamespace(state='paused',pending=None,ready_players=()))
            experiment.bind_world(world,Engine(),offers)
            class Clock:
                now=0.
                def monotonic(self): self.now+=.1;return self.now
            clock=Clock();result={}
            try:
                with patch.object(module.time,'monotonic',side_effect=clock.monotonic), \
                     patch.object(module.base.client,'game_identity',side_effect=lambda proc,*_:proc), \
                     patch.object(module.base.live,'steam_identity',return_value='initial-steam'):
                    experiment.on_ready(world=world,server_proc='server',server_started=1,server_identity='server',
                        client_proc='client',client_started=2,client_identity='client',game=root,out=root,
                        deadline=100,result=result,steam_identity='initial-steam')
            finally: experiment.close()
            self.assertEqual(calls,['invalidate','close','resume','pause'])
            self.assertTrue(result['npc_flight_experiment']['bridge_pause_confirmed'])
            self.assertFalse(result['npc_flight_experiment']['client_admitted'])
            progress=(root/'npc-flight-progress.log').read_text()
            self.assertIn('terminal_fence_confirmed',progress)
            self.assertIn('bridge_pause_confirmed',progress)
            self.assertNotIn(experiment.flight_lease,progress)

    def test_guard_uses_pilot_reference_from_one_shot_order(self):
        fixture=ET.parse(ROOT/'tools/dev/authority_npc_flight_fixture.xml')
        cue=fixture.find(".//cue[@name='Order']")
        self.assertEqual(cue.get('namespace'),'this')
        self.assertIsNotNone(cue.find(".//set_value[@name='$pilot'][@exact='$ship.pilot']"))
        guard=(ROOT/'tools/dev/authority_npc_flight_guard.xml').read_text()
        self.assertIn('$ship.pilot == md.X4AuthorityNPCFlightFixture.Order.$pilot',guard)

    @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'),'C compiler and LuaJIT required')
    def test_source_emits_the_reference_used_for_rate_without_any_native_setter(self):
        with tempfile.TemporaryDirectory() as temp:
            lib=Path(temp)/'fake-x4.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_npc_source_fake_x4.c','-o',str(lib)],
                           cwd=ROOT,check=True,capture_output=True,text=True,timeout=10)
            for variant in ([],['pause-loss'],['pause-and-stop'],['changed-actor']):
                with self.subTest(variant=variant):
                    subprocess.run(['luajit','tests/lua/authority_npc_source_probe.lua',str(lib),*variant],
                                   cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)

    def test_private_overlays_only_source_has_flight_driver_and_pilot(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'server/case';guest=root/'client/case'
            for case in (source,guest):
                lab=case/'extensions/x4_lan_lab'
                (lab/'ui').mkdir(parents=True);(lab/'md').mkdir();(lab/'native').mkdir()
                (lab/'ui/config.lua').write_text('X4LAN_CONFIG = {}\n')
                (lab/'ui.xml').write_text('    <file name="ui/authority_checkpoint_marker_probe.lua" />\n')
                (lab/'ui/authority_world_bridge_probe.lua').write_text(' if not started and now-loaded_at>=3 and not X4LAN_AUTHORITY_MARKER_READY() then return end\n')
            (source/'extensions/x4_lan_lab/native/x4lan_net.so').write_bytes(b'test')
            exp=module.FlightExperiment(flight_seconds=10,bridge_timeout=1)
            try:
                exp.install(source,'save');exp.install(guest,'load')
                sl=source/'extensions/x4_lan_lab';gl=guest/'extensions/x4_lan_lab'
                self.assertIsNotNone(ET.parse(sl/'md/authority_create_test_fixture.xml').find('.//create_ship/pilot/select'))
                self.assertIsNone(ET.parse(gl/'md/authority_create_test_fixture.xml').find('.//create_ship/pilot'))
                self.assertTrue((sl/'ui/authority_npc_flight_source.lua').is_file())
                self.assertFalse((gl/'ui/authority_npc_flight_source.lua').exists())
                self.assertTrue((gl/'ui/authority_npc_flight_guest_trace.lua').is_file())
                self.assertFalse((sl/'ui/authority_npc_flight_guest_trace.lua').exists())
                self.assertIn(gl/'md/authority_npc_flight_guard.xml',exp.protected(guest))
                src=(sl/'ui/authority_npc_flight_source.lua').read_text()
                self.assertNotIn('SetObjectSectorPos',src)
                self.assertNotIn('Unpause(',src)
                self.assertIn(exp.flight_lease,(sl/'ui/config.lua').read_text())
            finally: exp.close()
            self.assertNotIn(exp.flight_lease,(sl/'ui/config.lua').read_text())
