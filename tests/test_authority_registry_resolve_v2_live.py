"""Synthetic private overlay, log validation and callbacks; never starts X4."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('resolve_v2_live',ROOT/'tools/dev/authority_registry_resolve_v2_live.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class ResolveV2LiveTest(unittest.TestCase):
    def test_mocked_supervisor_confirms_pause_and_owned_cleanup(self):
        self.run_supervisor(False)

    def test_late_duplicate_during_cleanup_invalidates_success(self):
        self.run_supervisor(True)

    def run_supervisor(self,late_duplicate):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);game=root/'game';game.mkdir();(game/'X4').write_bytes(b'fake');(game/'extensions').mkdir()
            auth=root/'xauth';auth.write_text('fake');out=root/'out';calls=[]
            lease,epoch='a'*32,'b'*32
            shape='[X4LAN] AUTH_RESOLVE_V2 SHAPE stage={} type=table fields=actor,epoch,index,request_id,status actor_type={}\n'
            prefix='[X4LAN] AUTH_RESOLVE_V2 '
            log=shape.format('ok','number')+prefix+'ACTOR_MATCH\n'+shape.format('unavailable','nil')+prefix+'UNAVAILABLE\n'+prefix+'DONE\n'
            class Sock:
                def bind(self,_): pass
                def settimeout(self,_): pass
                def getsockname(self): return ('127.0.0.1',1001)
                def recvfrom(self,_): return f'HELLO|{lease}|{epoch}'.encode(),('127.0.0.1',1002)
                def close(self): calls.append('socket-close')
            class Process:
                pid=42
                def poll(self): return None
            class Bridge:
                def __init__(self,**_): pass
                def pause(self): calls.append('pause')
            def prepare(target,*_):
                case=target/'case';profile=case/'home/.config/EgoSoft/X4/45841'
                (profile/'save').mkdir(parents=True);(profile/'engine-output.log').write_text(log)
                (case/'extensions/x4_lan_lab/ui').mkdir(parents=True)
                return case,profile,[],case/'lock'
            def install(case,profile,**kw):
                (case/'extensions/x4_lan_lab/ui/config.lua').write_text('authority_control_lease="'+kw['lease']+'"\n')
            def stop(*_):
                calls.append('cleanup')
                if late_duplicate:
                    path=out/'case/home/.config/EgoSoft/X4/45841/engine-output.log'
                    with path.open('a') as stream: stream.write(prefix+'DONE\n')
                return []
            args=types.SimpleNamespace(game=game,out=out,display=':9',timeout=100.,seed=1)
            with patch.dict(M.os.environ,{'XAUTHORITY':str(auth)}), \
                 patch.object(M.snapshot,'output_path',return_value=out), \
                 patch.object(M.snapshot,'prepare_case',side_effect=prepare), \
                 patch.object(M.snapshot,'command_for',return_value=['fake']), \
                 patch.object(M.snapshot,'stop_owned',side_effect=stop), \
                 patch.object(M.live,'sha',return_value=M.live.EXE_SHA), \
                 patch.object(M.live,'x4_executables',return_value=[]), \
                 patch.object(M.live,'steam_identity',return_value='steam'), \
                 patch.object(M.live,'create_lock_target',return_value=(9,'lock')), \
                 patch.object(M.live,'release_lock_target'), \
                 patch.object(M.live,'start_ticks',return_value=1), \
                 patch.object(M.process_utils,'game_identity',return_value=(99,1)), \
                 patch.object(M.shutil,'which',return_value='/fake/bwrap'), \
                 patch.object(M.secrets,'token_hex',side_effect=[lease,epoch,'c'*32,'d'*32]), \
                 patch.object(M.socket,'socket',return_value=Sock()), \
                 patch.object(M.subprocess,'Popen',return_value=Process()), \
                 patch.object(M,'LocalControlBridge',Bridge),patch.object(M,'install',side_effect=install):
                result=M.run(args)
            self.assertEqual(result['success'],not late_duplicate,result)
            if late_duplicate: self.assertIn('final log invalid',result['error'])
            self.assertTrue(result['native_pause_confirmed'])
            self.assertTrue(result['owned_cleanup_confirmed']);self.assertEqual(calls,['pause','socket-close','cleanup'])
            self.assertNotIn(lease,(out/'case/extensions/x4_lan_lab/ui/config.lua').read_text())

    def test_overlay_has_no_save_or_ship_create_and_uses_one_update_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';profile=case/'home/45841'
            ui.mkdir(parents=True);(lab/'md').mkdir();(profile/'save').mkdir(parents=True)
            def bridge(*_):
                (ui/'config.lua').write_text('X4LAN_CONFIG = {authority_control_lease="'+'a'*32+'"}\n')
                (ui/'authority_world_bridge_probe.lua').write_text(' if not started and now-loaded_at>=3 then\n')
                (lab/'ui.xml').write_text('    <file name="ui/authority_world_bridge_probe.lua" />\n')
            with patch.object(M.world_bridge,'install_probe',side_effect=bridge):
                M.install(case,profile,port=1000,lease='a'*32,epoch='b'*32,id1='c'*32,id2='d'*32)
            self.assertIn('X4LAN_RESOLVE_V2_NATIVE_READY', (ui/'authority_world_bridge_probe.lua').read_text())
            self.assertTrue((lab/'md/authority_registry_resolve_v2.xml').exists())
            self.assertFalse((lab/'md/authority_identity_fixture.xml').exists())
            self.assertNotIn('SetScript(', (ui/'authority_registry_resolve_v2_native.lua').read_text())
            self.assertEqual((ui/'config.lua').stat().st_mode & 0o777,0o600)

    def test_log_requires_both_distinct_responses(self):
        shape='[X4LAN] AUTH_RESOLVE_V2 SHAPE stage={} type=table fields=actor,epoch,index,request_id,status actor_type={}\n'
        prefix='[X4LAN] AUTH_RESOLVE_V2 '
        good=shape.format('ok','number')+prefix+'ACTOR_MATCH\n'+shape.format('unavailable','nil')+prefix+'UNAVAILABLE\n'+prefix+'DONE\n'
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'log';log.write_text(good);self.assertTrue(M.check_log(log)['actor_match_observed'])
            for bad in (good.replace(prefix+'UNAVAILABLE\n',''),good+prefix+'DONE\n',good+prefix+'ERROR pause_lost\n',
                        shape.format('unavailable','nil')+prefix+'ACTOR_MATCH\n'+shape.format('ok','number')+prefix+'UNAVAILABLE\n'+prefix+'DONE\n'):
                log.write_text(bad)
                with self.assertRaises(ValueError): M.check_log(log)
            log.write_text(good+prefix+'ERROR pause_lost\n');self.assertTrue(M.probe_fault(log))

    def test_pause_timeout_reserves_deadline(self):
        self.assertEqual(M.pause_timeout(2.),1.)
        self.assertEqual(M.pause_timeout(100.),10.)
        for remaining in (1.99,0.,float('nan'),float('inf')):
            with self.assertRaises(TimeoutError): M.pause_timeout(remaining)

    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_probe_callbacks(self):
        for mode in ('ok','invalid-table','pause-loss','dispatch-false'):
            with self.subTest(mode=mode):
                subprocess.run(['luajit','tests/authority_registry_resolve_v2_native.lua',mode],cwd=ROOT,
                               capture_output=True,text=True,check=True,timeout=5)


if __name__=='__main__': unittest.main()
