-- The installed participant owner must reject pause before native dispatch.
local frame,logs,submissions=nil,{},0
local motion_state='ready'
local input={}
X4LAN_CONFIG={authority_participant_port=1234,authority_participant_lease=('a'):rep(32),
 authority_ticket={world_epoch=('b'):rep(32)},authority_client_motion_enabled=true,
 authority_client_motion_saved_playback_fixture='recovery_enh_870'}
function SetScript(name,callback)assert(name=='onUpdate' and not frame);frame=callback end
function DebugError(value)logs[#logs+1]=value end
function GetCurRealTime()return 1 end
function X4LAN_RECOVERED_CLIENT_LOAD_READY()return true end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
X4LAN_AUTHORITY_CONTROL_STATE={new=function()return {
 on_update=function()return true end,submit=function()submissions=submissions+1;return true end}end}
package.loadlib=function()return function()return {open=function()return {
 send=function()return true end,receive=function()return table.remove(input,1)end}end,monotonic=function()return 1 end}end end
X4LAN_LOCAL_UDP_MODULE=dofile('src/authority/lua/local_udp_module.lua')
X4LAN_RECOVERED_CLIENT_MOTION={new_x4=function(options)
 assert(options.saved_playback_fixture=='recovery_enh_870')
 return {tick=function()return true end,state=function()return motion_state end}
end}
dofile(arg[1]);frame();assert(#logs==0)
if arg[2]=='stopped' then motion_state='stopped' end
input[1]='CMD|'..('a'):rep(32)..'|'..('b'):rep(32)..'|1|pause'
frame()
if arg[2]=='stopped' then assert(submissions==1 and #logs==0)
else assert(submissions==0 and #logs==1 and logs[1]:find('AUTH_PARTICIPANT ERROR',1,true))end
print('installed owner enforces STOP before pause dispatch')
