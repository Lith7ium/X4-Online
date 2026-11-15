"""Injected Lua doubles only: these tests do not start X4 or establish a save."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LUAJIT = shutil.which('luajit')

COMMON = r'''
local core=assert(loadfile('src/authority/lua/control_state.lua'))()
local real,game,paused=0,100,false
local called={pause=0,resume=0,save=0};local reports={};local control
local engine={
 ready=function() return true end,
 real_time=function() return real end,game_time=function() return game end,
 is_paused=function() return paused end,
 pause=function() called.pause=called.pause+1 end,
 resume=function() called.resume=called.resume+1 end,
 saving_possible=function() return true end,
 save=function(slot) assert(slot=='save_009');called.save=called.save+1 end,
}
local cfg={enabled=true,owner='supervisor-1',world_epoch='epoch-1',timeout_seconds=2,pause_settle_seconds=.1}
local function report(row) reports[#reports+1]=row end
local function start() control=assert(core.new(cfg,engine,report)) end
local function submit(id,op,params) return control:submit('supervisor-1','epoch-1',id,op,params) end
local function confirm_pause()
 assert(submit(1,'pause'));paused=true;real=.1;assert(control:on_update());real=.21
 local ok,result=control:on_update();assert(ok and result=='confirmed')
end
'''


@unittest.skipUnless(LUAJIT, 'requires LuaJIT')
class ControlTests(unittest.TestCase):
    def lua(self, code):
        result=subprocess.run([LUAJIT,'-'],input=COMMON+code,text=True,cwd=ROOT,
                              capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_inactive_until_explicit_and_no_automatic_engine_calls(self):
        self.lua(r'''
assert(not core.new(nil,nil,nil));assert(not core.new({enabled=false},nil,nil))
local x4=assert(loadfile('src/authority/lua/x4_control_engine.lua'))()
assert(X4LAN_AUTHORITY_CONTROL_STATE==core and X4LAN_AUTHORITY_X4_CONTROL_ENGINE==x4)
assert(not x4.new(nil));assert(not x4.register_save_event(nil,nil,nil))
assert(called.pause==0 and called.resume==0 and called.save==0)
''')

    def test_pause_resume_wait_for_state_and_clock_and_reject_other_owner(self):
        self.lua(r'''
start();cfg.owner='changed';cfg.world_epoch='changed' -- constructor pinned both
assert(not control:submit('other','epoch-1',1,'pause'))
assert(not control:submit('supervisor-1','old',1,'pause'))
assert(submit(1,'pause'));assert(called.pause==1 and #reports==0)
assert(not submit(1,'pause'));assert(called.pause==1)
real=.05;assert(control:on_update());assert(#reports==0)
paused=true;real=.1;assert(control:on_update());real=.15;game=101
assert(control:on_update());real=.26;local ok,r=control:on_update()
assert(ok and r=='confirmed' and #reports==1 and reports[1].reason=='pause_observed')
assert(not submit(1,'pause'));assert(submit(2,'resume'));assert(called.resume==1 and #reports==1)
real=.3;assert(control:on_update());paused=false;real=.31;assert(control:on_update());assert(#reports==1)
game=102;real=.4;assert(control:on_update());assert(#reports==2 and reports[2].reason=='resume_observed')
''')

    def test_save_requires_pause_exclusivity_and_native_event_not_file_confirmation(self):
        self.lua(r'''
start()
local args={slot='save_009',exclusive_owner=true,empty_owned_slot=true}
assert(not submit(1,'save',args));assert(called.save==0) -- cannot save without observed pause
-- New process/state after the refused unsafe request.
start();confirm_pause()
assert(not submit(2,'save',{slot='save_009',exclusive_owner=true}))
assert(not submit(2,'save',{slot='../save_009',exclusive_owner=true,empty_owned_slot=true}))
assert(submit(2,'save',args));assert(called.save==1 and #reports==1)
real=.3;local ok,result=control:on_update();assert(ok and result=='pending' and #reports==1)
assert(control:on_game_saved(true));real=.4;ok,result=control:on_update()
assert(ok and result=='native_event_only' and #reports==2)
assert(reports[2].status=='native_event_only' and reports[2].reason=='file_verification_required')
assert(not submit(3,'save',args) and called.save==1)
assert(submit(3,'resume') and called.resume==1)
''')

    def test_timeout_late_events_failures_and_loss_of_pause_fence_the_process(self):
        self.lua(r'''
start();confirm_pause()
local args={slot='save_009',exclusive_owner=true,empty_owned_slot=true}
assert(submit(2,'save',args));real=3;local ok,reason=control:on_update()
assert(not ok and reason=='timeout' and reports[#reports].status=='failed')
assert(not control:on_game_saved(true));assert(not submit(3,'save',args));assert(called.save==1)
-- A synchronous foreign callback inside Pause cannot leave a false pending request.
real=0;game=100;paused=false;engine.pause=function() control:on_game_saved(true) end
start();local submitted,refusal=submit(1,'pause');assert(not submitted and refusal=='foreign_save_event')
engine.pause=function() called.pause=called.pause+1 end
-- A failing event during an observation cannot continue using a cleared request.
real=0;game=100;paused=false;start();confirm_pause();assert(submit(2,'save',args))
engine.ready=function() control:on_game_saved(false);return true end
local frame_ok,accepted,why=pcall(function() return control:on_update() end)
assert(frame_ok and not accepted and why=='faulted');engine.ready=function() return true end
-- An unsolicited completion means the exclusive save owner is no longer established.
real=0;game=100;paused=false;start();assert(not control:on_game_saved(true));assert(not submit(1,'pause'))
-- If the pause goes away while saving, a later event cannot establish a checkpoint.
real=0;game=100;paused=false;start();confirm_pause();assert(submit(2,'save',args))
paused=false;real=.3;ok,reason=control:on_update();assert(not ok and reason=='save_pause_lost')
assert(not control:on_game_saved(true))
''')

    def test_verified_checkpoint_allows_later_save_and_owned_slot_reuse(self):
        self.lua(r'''
cfg.enable_verified_reuse=true
local saves={};engine.save=function(slot,title) saves[#saves+1]={slot,title} end
start();confirm_pause()
local fresh={slot='save_009',exclusive_owner=true,empty_owned_slot=true}
assert(submit(2,'save',fresh));assert(saves[1][2]=='X4 Authority epoch-1 2')
assert(control:on_game_saved(true));real=.3;assert(control:on_update())
assert(reports[#reports].status=='native_event_only' and reports[#reports].title==saves[1][2])
local ok,why=submit(3,'resume');assert(not ok and why=='save_verification_required')
assert(not control:confirm_save('supervisor-1','epoch-1',1,true))
assert(not control:confirm_save('other','epoch-1',2,true))
assert(control:confirm_save('supervisor-1','epoch-1',2,true))
assert(submit(3,'resume'));paused=false;game=101;real=.4;assert(control:on_update())
assert(submit(4,'pause'));paused=true;real=.5;assert(control:on_update());real=.7;assert(control:on_update())
assert(not submit(5,'save',fresh)) -- a used slot cannot be asserted empty
assert(not submit(5,'save',{slot='save_010',exclusive_owner=true,overwrite_verified_owned_slot=true}))
local reused={slot='save_009',exclusive_owner=true,overwrite_verified_owned_slot=true}
assert(submit(5,'save',reused));assert(saves[2][2]=='X4 Authority epoch-1 5')
assert(control:on_game_saved(true));real=.8;assert(control:on_update())
assert(control:confirm_save('supervisor-1','epoch-1',5,true));assert(submit(6,'resume'))
assert(#saves==2)
''')

    def test_failed_or_unexpected_save_event_fences_reuse(self):
        self.lua(r'''
cfg.enable_verified_reuse=true;engine.save=function() end
local args={slot='save_009',exclusive_owner=true,empty_owned_slot=true}
start();confirm_pause();assert(submit(2,'save',args));assert(control:on_game_saved(true))
real=.3;assert(control:on_update());assert(not control:confirm_save('supervisor-1','epoch-1',2,false))
assert(not submit(3,'resume'))
real=0;game=100;paused=false;start();confirm_pause();assert(submit(2,'save',args))
assert(control:on_game_saved(true));real=.3;assert(control:on_update());paused=false
assert(not control:confirm_save('supervisor-1','epoch-1',2,true));assert(not submit(3,'resume'))
real=0;game=100;paused=false;start();confirm_pause();assert(submit(2,'save',args))
assert(control:on_game_saved(true));real=.3;assert(control:on_update())
assert(not control:on_game_saved(true));assert(not control:confirm_save('supervisor-1','epoch-1',2,true))
''')

    def test_immediate_event_duplicate_failure_and_report_exception(self):
        self.lua(r'''
local args={slot='save_009',exclusive_owner=true,empty_owned_slot=true}
start();confirm_pause()
engine.save=function() control:on_game_saved(false) end
local ok,why=submit(2,'save',args);assert(not ok and why=='save_event_failure')
-- An event emitted synchronously during SaveGame is still recorded, not lost.
real=0;game=100;paused=false;engine.save=function() assert(control:on_game_saved(true)) end
start();confirm_pause();assert(submit(2,'save',args));real=.3
ok,why=control:on_update();assert(ok and why=='native_event_only')
-- A native call error after an immediate event cannot become a save receipt.
real=0;game=100;paused=false;engine.save=function() control:on_game_saved(true);error('uncertain') end
start();confirm_pause();ok,why=submit(2,'save',args);assert(not ok and why=='save_call')
assert(reports[#reports].status=='failed' and not control:on_update())
-- Duplicate events prior to the next UI frame cannot be confused with a save.
real=0;game=100;paused=false;engine.save=function() end
start();confirm_pause();assert(submit(2,'save',args));assert(control:on_game_saved(true))
ok,why=control:on_game_saved(true);assert(not ok and why=='duplicate_save_event')
-- The report callback cannot reenter and issue a second command.
real=0;game=100;paused=false;local nested
control=assert(core.new(cfg,engine,function() nested={submit(2,'resume')} end))
assert(submit(1,'pause'));paused=true;real=.1;assert(control:on_update());real=.3;assert(control:on_update())
assert(nested[1]==false and nested[2]=='reentrant_report')
-- A failed receipt callback must not appear confirmed.
real=0;game=100;paused=false;control=assert(core.new(cfg,engine,function() error('offline') end))
assert(submit(1,'pause'));paused=true;real=.1;assert(control:on_update());real=.3
ok,why=control:on_update();assert(not ok and why=='report_failed' and not submit(2,'resume'))
''')

    def test_explicit_x4_bindings_registration_and_profile_guard(self):
        self.lua(r'''
local calls={};local callbacks={};local fakeffi={NULL=false,cdef=function() end,string=function(s) return s end}
fakeffi.C={GetSaveFolderPath=function() return 'C:\\sandbox\\45841\\save' end,
 IsPlayerValid=function() return true end,IsGamePaused=function() return false end,
 GetCurrentGameTime=function() return 123 end}
package.loaded.ffi=fakeffi
Pause=function() calls[#calls+1]='pause' end;Unpause=function() calls[#calls+1]='resume' end
local saved_title
SaveGame=function(slot,title) saved_title=title;calls[#calls+1]='save:'..slot end
IsSavingPossible=function(v) assert(v==false);return true end
GetCurRealTime=function() return 55 end
local x4=assert(loadfile('src/authority/lua/x4_control_engine.lua'))()
local binding=x4.new({enabled=true,test_profile='45841'})
assert(binding.ready() and not binding.is_paused() and binding.game_time()==123 and binding.real_time()==55)
assert(binding.saving_possible() and #calls==0)
binding.pause();binding.resume();binding.save('save_009')
assert(table.concat(calls,',')=='pause,resume,save:save_009')
assert(saved_title=='X4 Authority isolated checkpoint')
binding.save('save_009','X4 Authority epoch-1 2');assert(saved_title=='X4 Authority epoch-1 2')
local state={on_game_saved=function(_,v) calls[#calls+1]=tostring(v) end}
local register=function(name,fn) assert(name=='gameSaved');callbacks[#callbacks+1]=fn end
assert(x4.register_save_event({enabled=true},state,register));assert(#callbacks==1)
callbacks[1](nil,true);assert(calls[#calls]=='true')
assert(not pcall(x4.register_save_event,{enabled=true},state,register))
local unknown={on_game_saved=function() end}
assert(not pcall(x4.register_save_event,{enabled=true},unknown,function() error('uncertain registration') end))
assert(not pcall(x4.register_save_event,{enabled=true},unknown,register))
fakeffi.C.GetSaveFolderPath=function() return '/normal/profile/save' end
assert(not pcall(x4.new,{enabled=true,test_profile='45841'}))
''')


if __name__=='__main__':
    unittest.main()
