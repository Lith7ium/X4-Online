-- Execute the generated recovery probe with real witness Lua and X4 doubles.
local script,mode=assert(arg[1]),assert(arg[2])
local phase=mode=='standalone_create' and 'create' or 'verify'
local now,paused=0,true;local update;local events={};local pending;local packets={};local sent={};local logs={};local bridge_updates=0
package.loaded.ffi={cdef=function()end,C={IsPlayerValid=function()return true end,
 IsGamePaused=function()return paused end,IsSaveListLoadingComplete=function()return true end,ReloadSaveList=function()end}}
local net={send=function(_,v)sent[#sent+1]=v;return true end,pending=function()return #packets>0 end,receive=function()return table.remove(packets,1)end}
package.loadlib=function()return function()return {open=function()return net end}end end
X4LAN_CONFIG={authority_world_bridge=true,test_profile='45841',authority_control_port=1234,
 authority_control_lease=string.rep('a',32),authority_world_epoch=string.rep('b',32),authority_marker_required=true,
 authority_registry_nonce=string.rep('a',32),authority_registry_expected=string.rep('b',32)..'|2'}
X4LAN_AUTHORITY_RECOVERY_READY=function()return true end
X4LAN_AUTHORITY_RECOVERY_UPDATE=function()end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {} end,register_save_event=function()return true end}
X4LAN_AUTHORITY_LOCAL_CONTROL_BRIDGE={new=function()return {update=function()bridge_updates=bridge_updates+1;return true end}end}
X4LAN_RECOVERY_REGISTRY_STATUS={new=function()return {begin=function()return true end,tick=function()return true end,ready=function()return true end}end}
dofile('src/authority/lua/recovery_registry_witness.lua')
GetCurRealTime=function()return now end;GetSaveList=function()return {} end
SetScript=function(_,f)update=f end;RegisterEvent=function(name,f)events[name]=f;return true end
AddUITriggeredEvent=function(screen,op,args)assert(screen=='X4AuthorityRegistryWitness');pending={op,args};return true end
DebugError=function(msg)logs[#logs+1]=msg end
local function has(needle)for _,v in ipairs(logs)do if v:find(needle,1,true)then return true end end;return false end
local function reply(kind,index)
 local p=assert(pending);pending=nil
 assert(events['X4AuthorityRegistryWitness.Result'])(nil,p[2].request_id..'|'..string.rep('b',32)..'|'..kind..'|'..index..'|ok')
end
assert(loadfile(script))();update();now=4;update();assert(pending[1]==(phase=='create' and 'Initialize' or 'BeginVerify'));reply(phase=='create' and 'init' or 'begin',0)
if mode=='pause_before_done' then
 paused=false;update();assert(has('not_paused') and has('AUTH_WORLD_BRIDGE ERROR') and #sent==0);return
end
for i=1,2 do update();assert(pending[1]=='Step');reply(phase,i)end
update();assert(pending[1]=='Finish');reply('finish',2)
assert(has('|'..phase..'|sealed'))
update();local prefix=string.rep('a',32)..'|'..string.rep('b',32)
assert(sent[1]=='RECOVERY_READY|'..prefix)
packets[1]='ACTIVATE|'..prefix;update();assert(sent[2]=='ACTIVATED|'..prefix)
update();assert(bridge_updates==1)
paused=false;update()
if mode=='standalone' or mode=='standalone_create' then
 assert(has('not_paused') and has('AUTH_WORLD_BRIDGE ERROR'));return
end
assert(mode=='join' and bridge_updates==2 and not has('not_paused'))
-- A late duplicate remains a fault and is not masked by completed state.
assert(not pcall(events['X4AuthorityRegistryWitness.Result'],nil,'late'))
assert(has('event_state'));update();assert(has('AUTH_WORLD_BRIDGE ERROR') and bridge_updates==2)
