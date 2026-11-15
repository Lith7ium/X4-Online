"""Isolated harness composition and control ordering; never launches X4."""
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
import authority_control_live as live
from authority.checkpoints import CheckpointStore


class ControlLiveTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'),'requires a C compiler')
    def test_private_case_load_order_and_no_gate_or_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';lab=case/'extensions/x4_lan_lab'
            for folder in ('ui','md','native'):
                (lab/folder).mkdir(parents=True,exist_ok=True)
            (lab/'ui/config.lua').write_text('old')
            (lab/'ui/x4ls_autostart.lua').write_text('-- stub')
            (lab/'ui/native_gate_snapshot.lua').write_text('error("must not load")')
            (lab/'md/native_gate_battle.xml').write_text('<md/>')
            lease='a'*32
            live.install_probe(case,12345,lease)
            ui=(lab/'ui.xml').read_text()
            self.assertLess(ui.index('ui/control_state.lua'),ui.index('ui/authority_control_probe.lua'))
            self.assertLess(ui.index('ui/x4_control_engine.lua'),ui.index('ui/authority_control_probe.lua'))
            self.assertNotIn('native_gate',ui)
            self.assertFalse((lab/'ui/native_gate_snapshot.lua').exists())
            self.assertTrue((lab/'native/x4lan_net.so').is_file())
            self.assertEqual(stat.S_IMODE((lab/'ui/config.lua').stat().st_mode),0o600)
            self.assertIn(lease,(lab/'ui/config.lua').read_text())

    def test_receipt_order_verified_file_and_udp_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);profile=root/'profile';(profile/'save').mkdir(parents=True)
            storage=root/'store';storage.mkdir();store=CheckpointStore(storage)
            with self.assertRaises(ValueError): live.verify_and_commit(profile,store)
            save=profile/'save'/live.snapshot.SLOT
            save.write_bytes(gzip.compress(b'<savegame><world/></savegame>'))
            checkpoint=live.verify_and_commit(profile,store)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
                receiver.bind(('127.0.0.1',0));receiver.settimeout(1)
                with self.assertRaises(ValueError): live.send_verified(sender,receiver.getsockname(),'a'*32,None)
                live.send_verified(sender,receiver.getsockname(),'a'*32,checkpoint)
                self.assertEqual(receiver.recv(512),('VERIFIED|'+'a'*32).encode())
            save.write_bytes(b'not-gzip')
            with self.assertRaises(ValueError): live.verify_and_commit(profile,store)

    def test_incremental_log_retains_order_across_large_growth_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'engine-output.log';watch=live.ControlLogWatch(path)
            self.assertFalse(watch.poll())
            with path.open('wb') as f:
                f.write(b'[X4LAN] AUTH_CONTROL ARMED\n')
                f.write(b'X4 ordinary noise\n' * 100000)  # more than one MiB
            while not watch.poll(): pass
            self.assertEqual(watch.counts,[1,0,0,0,0])
            with path.open('ab') as f:
                for marker in live.MARKERS[1:]:
                    f.write(('[X4LAN] '+marker+'\n').encode())
            while not watch.poll(): pass
            self.assertEqual(watch.counts,[1]*5)
            with path.open('ab') as f: f.write(b'[X4LAN] AUTH_CONTROL ARMED\n')
            with self.assertRaisesRegex(ValueError,'duplicate'):
                watch.poll()
            path.unlink();path.write_text('replacement\n')
            with self.assertRaisesRegex(ValueError,'changed|replaced'):
                watch.poll()

    def test_incremental_log_rejects_out_of_order_and_bounded_partial_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log';watch=live.ControlLogWatch(path)
            path.write_bytes(b'[X4LAN] AUTH_CONTROL SAVE native_event_only\n')
            with self.assertRaisesRegex(ValueError,'out-of-order'): watch.poll()
            path.unlink();path.write_bytes(b'x'*(live.ControlLogWatch.MAX_LINE+1))
            watch=live.ControlLogWatch(path)
            with self.assertRaisesRegex(ValueError,'line exceeded'): watch.poll()

    @unittest.skipUnless(shutil.which('luajit'),'requires LuaJIT')
    def test_ui_driver_refuses_to_resume_before_verification(self):
        script=r'''
local paused,now,game=false,0,10
local cutscene,saving_ready=true,false
local reject_after_pause=os.getenv("AUTH_TEST_REJECT_POST_PAUSE")=="1"
local eligibility_checks={}
local calls={pause=0,save=0,resume=0};local logs={};local events={};local frames={};local incoming={}
local lease=string.rep('a',32)
X4LAN_CONFIG={authority_control_probe=true,test_profile='45841',authority_control_port=12345,authority_control_lease=lease}
local ffi={cdef=function() end,C={IsPlayerValid=function() return true end,
 IsSaveListLoadingComplete=function() return true end,ReloadSaveList=function() end,
 IsFullscreenCutsceneActive=function() return cutscene end}}
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
 saving_possible=function() eligibility_checks[#eligibility_checks+1]=paused;return saving_ready and not (paused and reject_after_pause) end,
 save=function(slot) assert(slot=='save_009');calls.save=calls.save+1 end}
X4LAN_AUTHORITY_CONTROL_STATE=assert(loadfile('src/authority/lua/control_state.lua'))()
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function() return engine end,
 register_save_event=function(_,state,reg) reg('gameSaved',function(_,v) state:on_game_saved(v) end);return true end}
assert(loadfile('tools/dev/authority_control_probe.lua'))()
frames.update();now=3.1;frames.update();assert(calls.pause==0 and #eligibility_checks==0)
cutscene=false;now=3.11;frames.update();assert(calls.pause==0 and #eligibility_checks==1 and eligibility_checks[1]==false)
saving_ready=true;now=3.12;frames.update();assert(calls.pause==1 and calls.save==0)
incoming={'VERIFIED|'..lease};now=3.23;frames.update();assert(calls.resume==0)
now=3.3;frames.update();assert(eligibility_checks[3]==true)
if reject_after_pause then
 assert(calls.save==0 and calls.resume==0)
 assert(table.concat(logs,'\n'):find('AUTH_CONTROL ERROR code=submit_saving_unavailable',1,true))
 return
end
assert(calls.save==1)
events.gameSaved(nil,true);now=3.4;frames.update()
for i=1,5 do now=now+.1;frames.update() end
assert(calls.resume==0)
incoming={'VERIFIED|'..string.rep('b',32)};now=4;frames.update();assert(calls.resume==0)
incoming={'VERIFIED|'..lease};now=4.1;frames.update();assert(calls.resume==1)
game=11;now=4.2;frames.update()
assert(table.concat(logs,'\n'):find('AUTH_CONTROL COMPLETE',1,true))
assert(calls.pause==1 and calls.save==1 and calls.resume==1)
'''
        for reject in ('0','1'):
            with self.subTest(reject_after_pause=reject):
                env={**os.environ,'AUTH_TEST_REJECT_POST_PAUSE':reject}
                result=subprocess.run(['luajit','-'],input=script,text=True,cwd=ROOT,capture_output=True,timeout=5,env=env)
                self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
