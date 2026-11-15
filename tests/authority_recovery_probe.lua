-- Isolated probe logic with fake UI functions; no X4 process or real files.
local menu,valid,paused=true,false,false
local events={};local frame;local loaded=0;local inspections=0;local pauses=0
package.loaded.ffi=nil
package.preload.ffi=function()
 return {cdef=function() end,NULL={},string=function(v)return v end,C={
  IsStartmenu=function()return menu end,IsPlayerValid=function()return valid end,
  IsGamePaused=function()return paused end,IsSaveListLoadingComplete=function()return true end,
  ReloadSaveList=function()end,GetSaveFolderPath=function()return '/private/save' end}}
end
X4LAN_CONFIG={authority_recovery_probe=true,test_profile='45841',authority_load_save_path='/private/save'}
DebugError=function(msg) events[#events+1]=msg end
SetScript=function(event,fn)assert(event=='onUpdate');frame=fn end
GetSaveList=function(filter)assert(filter.save_008);return {{filename='save_008'}}end
LoadGame=function(slot)assert(slot=='save_008');loaded=loaded+1;menu=false;valid=true end
Pause=function()pauses=pauses+1;paused=true end
X4LAN_AUTHORITY_MARKER_READY=function()inspections=inspections+1;return inspections>1 end
assert(loadfile('tools/dev/authority_recovery_probe.lua'))();frame();frame()
assert(loaded==1 and #events==1 and events[1]=='[X4LAN] AUTH_RECOVERY REQUEST')
-- LoadGame rebuilds the UI and the script's local state.
assert(loadfile('tools/dev/authority_recovery_probe.lua'))();frame();frame()
assert(inspections==1 and pauses==0 and #events==1)
frame();assert(inspections==2 and pauses==1 and #events==1)
frame();assert(#events==2 and events[2]=='[X4LAN] AUTH_RECOVERY PAUSED')
frame();assert(loaded==1 and pauses==1 and #events==2)
