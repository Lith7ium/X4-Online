-- Exercise the installed participant frame, with no game or network.
local ffi=require('ffi');ffi.cdef[[void TestPlayerValid(bool);]]
local frame,logs,created,ticks,ready=nil,{},0,0,false
X4LAN_CONFIG={authority_participant_port=1234,authority_participant_lease=('a'):rep(32),
 authority_ticket={world_epoch=('b'):rep(32)},authority_client_motion_enabled=true}
function SetScript(name,fn)assert(name=='onUpdate' and not frame);frame=fn end
function DebugError(v)logs[#logs+1]=v end
function GetCurRealTime()return 1 end
function X4LAN_RECOVERED_CLIENT_LOAD_READY()return ready end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
X4LAN_AUTHORITY_CONTROL_STATE={new=function()return {on_update=function()return true end}end}
package.loadlib=function()return function()return {open=function()return {
 send=function()return true end,receive=function()return nil end}end}end end
X4LAN_RECOVERED_CLIENT_MOTION={new_x4=function()
 created=created+1;return {tick=function()ticks=ticks+1;return true end}
end}
dofile(arg[1]);assert(frame)
ffi.C.TestPlayerValid(false);frame();assert(#logs==0 and created==0)
ffi.C.TestPlayerValid(true);ready=true;frame();assert(created==1 and ticks==1 and #logs==0)
ffi.C.TestPlayerValid(false);frame();assert(#logs==1 and logs[1]:find('AUTH_PARTICIPANT ERROR',1,true))
ffi.C.TestPlayerValid(true);frame();assert(created==1 and ticks==1 and #logs==1)
