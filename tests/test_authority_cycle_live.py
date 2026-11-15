"""Synthetic checks for the isolated two-cycle experiment; never launches X4."""
import gzip
import os
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
import authority_cycle_live as live
from authority.checkpoints import CheckpointStore


class CycleLiveTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'),'requires a C compiler')
    def test_private_extension_composes_two_cycle_probe_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';lab=case/'extensions/x4_lan_lab'
            for folder in ('ui','md','native'):
                (lab/folder).mkdir(parents=True,exist_ok=True)
            (lab/'ui/config.lua').write_text('old')
            (lab/'ui/x4ls_autostart.lua').write_text('-- stub')
            (lab/'ui/native_gate_snapshot.lua').write_text('error("must not load")')
            (lab/'md/native_gate_battle.xml').write_text('<md/>')
            live.install_probe(case,12345,'a'*32,'b'*32)
            ui=(lab/'ui.xml').read_text()
            self.assertLess(ui.index('ui/authority_cycle_control_state.lua'),ui.index('ui/authority_cycle_probe.lua'))
            self.assertLess(ui.index('ui/x4_control_engine.lua'),ui.index('ui/authority_cycle_probe.lua'))
            self.assertNotIn('native_gate',ui)
            self.assertFalse((lab/'ui/native_gate_snapshot.lua').exists())
            self.assertTrue((lab/'native/x4lan_net.so').is_file())
            self.assertEqual(stat.S_IMODE((lab/'ui/config.lua').stat().st_mode),0o600)

    def test_unauthorized_or_reordered_receipts_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log';watch=live.ControlLogWatch(path)
            path.write_bytes(b'[X4LAN] AUTH_CYCLE SAVE 2 native_event_only\n')
            with self.assertRaisesRegex(ValueError,'out-of-order'): watch.poll()
        with self.assertRaisesRegex(RuntimeError,'authorization'):
            live.require_authorized_resumes([1,1,1,1,0,0,0,0],set())
        with self.assertRaisesRegex(RuntimeError,'authorization'):
            live.require_authorized_resumes([1,1,1,1,1,1,1,0],{1})
        live.require_authorized_resumes([1,1,1,1,1,1,1,0],{1,2})

    def test_each_cycle_requires_its_own_new_slot_and_strictly_later_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);profile=root/'profile';(profile/'save').mkdir(parents=True)
            storage=root/'store';storage.mkdir();store=CheckpointStore(storage)
            cycle_id='a'*32
            def write(slot,cycle,time):
                (profile/'save'/slot).write_bytes(gzip.compress(
                    (f'<savegame><info><save name="X4 Authority cycle {cycle} {cycle_id}"/>'
                     f'<game time="{time}"/></info></savegame>').encode()))
            write('save_009.xml.gz',1,10)
            cp1,e1=live.verify_and_commit(profile,store,1,cycle_id)
            with self.assertRaises(ValueError): live.verify_and_commit(profile,store,2,cycle_id,e1.game_time)
            write('save_010.xml.gz',1,11)
            with self.assertRaises(ValueError): live.verify_and_commit(profile,store,2,cycle_id,e1.game_time)
            write('save_010.xml.gz',2,10)
            with self.assertRaises(ValueError): live.verify_and_commit(profile,store,2,cycle_id,e1.game_time)
            write('save_010.xml.gz',2,12)
            cp2,e2=live.verify_and_commit(profile,store,2,cycle_id,e1.game_time)
            self.assertNotEqual(cp1.checkpoint_id,cp2.checkpoint_id)
            self.assertGreater(e2.game_time,e1.game_time)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
                receiver.bind(('127.0.0.1',0));receiver.settimeout(1)
                with self.assertRaises(ValueError): live.send_verified(sender,receiver.getsockname(),'b'*32,2,cycle_id,None,e2)
                with self.assertRaises(ValueError): live.send_verified(sender,receiver.getsockname(),'b'*32,2,cycle_id,cp1,e1)
                live.send_verified(sender,receiver.getsockname(),'b'*32,2,cycle_id,cp2,e2)
                self.assertEqual(receiver.recv(512),('VERIFIED|'+'b'*32+'|2').encode())

    @unittest.skipUnless(shutil.which('luajit'),'requires LuaJIT')
    def test_two_cycle_driver_requires_each_correlated_authorization(self):
        script=r'''
local paused,now,game=false,0,10
local calls={pause=0,save=0,resume=0};local names={};local logs={};local events={};local frames={};local incoming={}
local lease=string.rep('a',32);local id=string.rep('c',32)
X4LAN_CONFIG={authority_cycle_probe=true,test_profile='45841',authority_control_port=12345,authority_control_lease=lease,authority_cycle_id=id}
local ffi={cdef=function() end,C={IsPlayerValid=function() return true end,
 IsSaveListLoadingComplete=function() return true end,ReloadSaveList=function() end,
 IsFullscreenCutsceneActive=function() return false end}}
package.loaded.ffi=ffi
GetCurRealTime=function() return now end
GetSaveList=function() return {} end
RegisterEvent=function(name,fn) events[name]=fn end
DebugError=function(msg) logs[#logs+1]=msg end
SetScript=function(name,fn) assert(name=='onUpdate');frames.update=fn end
local conn={send=function(_,v) assert(v=='HELLO|'..lease);return true end,
 receive=function() return table.remove(incoming,1) end}
package.loadlib=function() return function() return {open=function() return conn end} end end
local engine={ready=function() return true end,is_paused=function() return paused end,
 game_time=function() return game end,real_time=function() return now end,
 pause=function() calls.pause=calls.pause+1;paused=true end,
 resume=function() calls.resume=calls.resume+1;paused=false end,
 saving_possible=function() return true end,save=function() error('must be replaced') end}
SaveGame=function(slot,name) calls.save=calls.save+1;names[#names+1]={slot,name} end
X4LAN_AUTHORITY_CYCLE_CONTROL_STATE=assert(loadfile('tools/dev/authority_cycle_control_state.lua'))()
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function() return engine end,
 register_save_event=function(_,state,reg) reg('gameSaved',function(_,v) state:on_game_saved(v) end);return true end}
assert(loadfile('tools/dev/authority_cycle_probe.lua'))()
local function tick(t) now=t;frames.update() end
frames.update();tick(3.1);assert(calls.pause==1)
tick(3.21);tick(3.3);assert(calls.save==1 and names[1][1]=='save_009' and names[1][2]=='X4 Authority cycle 1 '..id)
events.gameSaved(nil,true);tick(3.4);tick(3.5);assert(calls.resume==0)
incoming={'VERIFIED|'..lease..'|2'};tick(3.6);assert(calls.resume==0)
incoming={'VERIFIED|'..lease..'|1'};tick(3.7);assert(calls.resume==1)
game=10.1;tick(3.8);tick(3.9);assert(calls.pause==1)
game=12;tick(4.0);assert(calls.pause==2)
tick(4.2);tick(4.3);assert(calls.save==2 and names[2][1]=='save_010' and names[2][2]=='X4 Authority cycle 2 '..id)
-- This could be a late first event; it is never sufficient to resume cycle 2.
events.gameSaved(nil,true);tick(4.4)
incoming={'VERIFIED|'..lease..'|1'};tick(4.5);assert(calls.resume==1)
incoming={'VERIFIED|'..lease..'|2'};tick(4.6);assert(calls.resume==2)
game=13;tick(4.7)
assert(table.concat(logs,'\n'):find('AUTH_CYCLE COMPLETE',1,true))
'''
        result=subprocess.run(['luajit','-'],input=script,text=True,cwd=ROOT,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
