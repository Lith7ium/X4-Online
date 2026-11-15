"""Focused synthetic tests for the private same-slot experiment; never starts X4."""
import gzip
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_reuse_live as live
from authority.checkpoints import CheckpointStore

class ReuseLiveTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'),'requires a C compiler')
    def test_private_overlay_installs_real_reuse_state_and_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';lab=case/'extensions/x4_lan_lab'
            for folder in ('ui','md','native'):
                (lab/folder).mkdir(parents=True,exist_ok=True)
            (lab/'ui/config.lua').write_text('old')
            (lab/'ui/native_gate_snapshot.lua').write_text('old')
            (lab/'md/native_gate_battle.xml').write_text('<md/>')
            live.install_probe(case,12345,'a'*32,'b'*32)
            ui=(lab/'ui.xml').read_text()
            self.assertLess(ui.index('ui/authority_control_state.lua'),ui.index('ui/authority_reuse_probe.lua'))
            self.assertEqual((lab/'ui/authority_control_state.lua').read_bytes(),
                             (ROOT/'src/authority/lua/control_state.lua').read_bytes())
            self.assertNotIn('native_gate',ui)
            self.assertEqual(stat.S_IMODE((lab/'ui/config.lua').stat().st_mode),0o600)

    def test_reused_slot_needs_new_title_and_later_time_before_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);profile=root/'profile';(profile/'save').mkdir(parents=True)
            store_dir=root/'store';store_dir.mkdir();store=CheckpointStore(store_dir)
            epoch='a'*32;save=profile/'save/save_009.xml.gz'
            def write(request_id,game_time):
                save.write_bytes(gzip.compress((f'<savegame><info><save name="X4 Authority {epoch} {request_id}"/>'
                                                f'<game time="{game_time}"/></info></savegame>').encode()))
            write(2,10);cp1,e1=live.verify_and_commit(profile,store,1,epoch)
            with self.assertRaises(ValueError): live.verify_and_commit(profile,store,2,epoch,e1.game_time)
            write(5,10)
            with self.assertRaises(ValueError): live.verify_and_commit(profile,store,2,epoch,e1.game_time)
            write(5,12);cp2,e2=live.verify_and_commit(profile,store,2,epoch,e1.game_time)
            self.assertNotEqual(cp1.sha256,cp2.sha256)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as recv, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as send:
                recv.bind(('127.0.0.1',0));recv.settimeout(1)
                with self.assertRaises(ValueError): live.send_verified(send,recv.getsockname(),'b'*32,2,epoch,cp1,e1)
                live.send_verified(send,recv.getsockname(),'b'*32,2,epoch,cp2,e2)
                self.assertEqual(recv.recv(512),('VERIFIED|'+'b'*32+'|2').encode())
            write(8,14);cp3,e3=live.verify_and_commit(profile,store,3,epoch,e2.game_time)
            self.assertNotEqual(cp2.sha256,cp3.sha256)
            self.assertGreater(e3.game_time,e2.game_time)
            self.assertEqual(store.get(cp1.checkpoint_id).sha256,cp1.sha256)
            self.assertEqual(store.get(cp2.checkpoint_id).sha256,cp2.sha256)
            with self.assertRaises(RuntimeError): live.require_authorized_resumes([1]*10+[0],{1,2})

    @unittest.skipUnless(shutil.which('luajit'),'requires LuaJIT')
    def test_probe_uses_real_state_and_each_independent_authorization(self):
        script=r'''
local paused,now,game=false,0,10
local saves,resumes,logs,events,frames,incoming={},{},{},{},{},{}
local lease=string.rep('a',32);local epoch=string.rep('c',32)
X4LAN_CONFIG={authority_reuse_probe=true,test_profile='45841',authority_control_port=12345,authority_control_lease=lease,authority_cycle_id=epoch}
package.loaded.ffi={cdef=function() end,C={IsPlayerValid=function() return true end,IsSaveListLoadingComplete=function() return true end,ReloadSaveList=function() end,IsFullscreenCutsceneActive=function() return false end}}
GetCurRealTime=function() return now end;GetSaveList=function() return {} end
RegisterEvent=function(name,fn) events[name]=fn end;DebugError=function(msg) logs[#logs+1]=msg end
SetScript=function(_,fn) frames.update=fn end
local conn={send=function() return true end,receive=function() return table.remove(incoming,1) end}
package.loadlib=function() return function() return {open=function() return conn end} end end
local engine={ready=function() return true end,is_paused=function() return paused end,game_time=function() return game end,real_time=function() return now end,
 pause=function() paused=true end,resume=function() resumes[#resumes+1]=true;paused=false end,saving_possible=function() return true end,save=function() error('not replaced') end}
SaveGame=function(slot,name) saves[#saves+1]={slot,name} end
X4LAN_AUTHORITY_CONTROL_STATE=assert(loadfile('src/authority/lua/control_state.lua'))()
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function() return engine end,register_save_event=function(_,state,reg) reg('gameSaved',function(_,v) state:on_game_saved(v) end);return true end}
assert(loadfile('tools/dev/authority_reuse_probe.lua'))()
local function tick(dt) now=now+dt;frames.update() end
frames.update();tick(3.1)
for cycle=1,3 do
 tick(.2);tick(.2)
 assert(#saves==cycle and saves[cycle][1]=='save_009' and saves[cycle][2]=='X4 Authority '..epoch..' '..(3*cycle-1))
 events.gameSaved(nil,true);tick(.1)
 incoming={'VERIFIED|'..lease..'|'..(cycle%3+1)};tick(.1);assert(#resumes==cycle-1)
 incoming={'VERIFIED|'..lease..'|'..cycle};tick(.1);assert(#resumes==cycle)
 game=game+3;tick(.1);tick(.1)
end
assert(table.concat(logs,'\n'):find('AUTH_REUSE COMPLETE',1,true))
'''
        result=subprocess.run(['luajit','-'],input=script,text=True,cwd=ROOT,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__': unittest.main()
