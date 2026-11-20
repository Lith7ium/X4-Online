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

-- Early mode pauses the first playable frame, even after the UI rebuild.
-- Hold the marker pending for multiple updates and delay pause confirmation.
X4LAN_CONFIG.authority_recovery_early_pause=true
local marker_ready,lose_pause_during_marker=false,false
Pause=function()pauses=pauses+1 end
X4LAN_AUTHORITY_MARKER_READY=function()
 assert(paused);inspections=inspections+1
 if lose_pause_during_marker then paused=false end
 return marker_ready
end
local function start_early(rebuild)
 menu,valid,paused=true,false,false
 events,loaded,inspections,pauses={},0,0,0
 marker_ready,lose_pause_during_marker=false,false
 assert(loadfile('tools/dev/authority_recovery_probe.lua'))()
 frame();frame()
 assert(loaded==1 and #events==1 and events[1]=='[X4LAN] AUTH_RECOVERY REQUEST')
 valid=false
 if rebuild then assert(loadfile('tools/dev/authority_recovery_probe.lua'))() end
 frame()
 assert(pauses==0 and inspections==0 and #events==1)
 valid=true
 frame()
 assert(pauses==1 and inspections==0 and #events==1)
 frame()
 assert(pauses==1 and inspections==0 and #events==1)
 paused=true
 frame();frame()
 assert(pauses==1 and inspections==2 and #events==1)
end
start_early(true)
marker_ready=true
frame();frame()
assert(pauses==1 and inspections==3 and #events==2 and events[2]=='[X4LAN] AUTH_RECOVERY PAUSED')

-- Lose a confirmed pause while still waiting for the marker.
start_early(false)
paused=false
frame();frame()
assert(pauses==1 and inspections==2 and #events==2 and events[2]=='[X4LAN] AUTH_RECOVERY ERROR')

-- A marker becoming ready cannot mask a pause lost during its inspection.
start_early(true)
marker_ready,lose_pause_during_marker=true,true
frame()
assert(pauses==1 and inspections==3 and #events==2 and events[2]=='[X4LAN] AUTH_RECOVERY ERROR')
