local menu=true;local valid=false;local paused=false;local loaded=0;local pauses=0;local refresh=0;local logs={}
local C={GetSaveFolderPath=function() return '/private/save' end,
 IsStartmenu=function() return menu end,IsPlayerValid=function() return valid end,
 IsGamePaused=function() return paused end,IsSaveListLoadingComplete=function() return true end,
 ReloadSaveList=function() refresh=refresh+1 end}
package.preload.ffi=function() return {C=C,NULL={},cdef=function() end,string=function(s) return s end} end
GetSaveList=function()return {{filename='save_009'}}end
LoadGame=function(s)assert(s=='save_009');loaded=loaded+1 end
Pause=function() pauses=pauses+1 end
DebugError=function(s)logs[#logs+1]=s end
local frame
SetScript=function(name,fn)assert(name=='onUpdate');frame=fn end
X4LAN_CONFIG={test_profile='45841',authority_download_load=true,authority_load_save_path='/private/save',
 authority_ticket={world_epoch='epoch',connection_handle=1,baseline_id=2,load_generation=3,
 checkpoint_id='checkpoint-'..string.rep('a',32),sha256=string.rep('b',64),attempt_id=string.rep('c',32),slot='save_009'}}
dofile('src/authority/lua/client_load_barrier.lua');dofile('src/authority/lua/x4_client_load_engine.lua')
dofile('tools/dev/authority_download_load_probe.lua')
frame();frame();assert(refresh==1 and loaded==1 and #logs==1 and logs[1]:find('load_requested|',1,true))
-- Simulate the Lua reinitialization by loading the probe afresh.
menu=false;valid=true;dofile('tools/dev/authority_download_load_probe.lua');frame();frame();frame()
assert(pauses==1 and #logs==1);paused=true;frame();frame()
assert(#logs==2 and logs[2]:find('pause_observed|',1,true))
