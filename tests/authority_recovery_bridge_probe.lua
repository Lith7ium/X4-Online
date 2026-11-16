-- Offline doubles for the generated private probe. Never loads X4.
local script=assert(arg[1]); local now=0; local ready=false; local paused=true
local update; local packets={}; local sent={}; local errors={}; local created,updates=0,0
local net={send=function(_,v) sent[#sent+1]=v;return true end,
 receive=function() return table.remove(packets,1) end}
package.loaded.ffi={cdef=function()end,C={IsPlayerValid=function()return true end,
 IsGamePaused=function()return paused end,IsSaveListLoadingComplete=function()return true end,
 ReloadSaveList=function()end}}
package.loadlib=function()return function()return {open=function()return net end}end end
X4LAN_CONFIG={authority_world_bridge=true,test_profile='45841',authority_control_port=1234,
 authority_control_lease=string.rep('a',32),authority_world_epoch=string.rep('b',32),authority_marker_required=true}
X4LAN_AUTHORITY_RECOVERY_READY=function()return ready end
X4LAN_AUTHORITY_RECOVERY_UPDATE=function()end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {} end,
 register_save_event=function()return true end}
X4LAN_AUTHORITY_LOCAL_CONTROL_BRIDGE={new=function()created=created+1;return {update=function()updates=updates+1;return true end}end}
GetCurRealTime=function()return now end;GetSaveList=function()return {} end
SetScript=function(_,f)update=f end;RegisterEvent=function()end
DebugError=function(msg)errors[#errors+1]=msg end
local prefix=string.rep('a',32)..'|'..string.rep('b',32)
assert(loadfile(script))();update();assert(#sent==0 and created==0)
ready=true;update();now=4;update()
assert(sent[1]=='RECOVERY_READY|'..prefix and created==0)
packets[1]='ACTIVATE|'..prefix;update();assert(sent[2]=='ACTIVATED|'..prefix and created==0)
update();assert(created==1 and #errors==0)
-- No heartbeat must fill the UDP queue while host-side save validation blocks;
-- the actual control bridge must still be serviced on every subsequent frame.
local before=updates
for _=1,1000 do now=now+.25;update() end
assert(#sent==2 and updates==before+1000 and #errors==0)
-- A new UI instance faults on an unexpected activation instead of enabling the bridge.
created=0;sent={};errors={};packets={};now=0
assert(loadfile(script))();update();now=4;packets[1]='ACTIVATE|wrong';update()
assert(created==0 and #errors==1);update();assert(created==0)
-- A pause loss before host activation also fences this instance.
created=0;sent={};errors={};packets={};now=0;paused=true
assert(loadfile(script))();update();now=4;paused=false;update()
assert(created==0 and #errors==1)
