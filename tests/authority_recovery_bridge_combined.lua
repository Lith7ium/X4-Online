-- Both generated UI scripts, in manifest order, with exactly one update owner.
local recovery,bridge=assert(arg[1]),assert(arg[2])
local menu,valid,paused=true,false,false
local now=0; local callbacks,update=0,nil; local messages={}; local loads=0
local sent={};local incoming={}
local net={send=function(_,value)sent[#sent+1]=value;return true end,
 receive=function()return table.remove(incoming,1) end}
package.loaded.ffi={cdef=function()end,NULL={},string=function(v)return v end,C={
 IsStartmenu=function()return menu end, IsPlayerValid=function()return valid end,
 IsGamePaused=function()return paused end,IsSaveListLoadingComplete=function()return true end,
 ReloadSaveList=function()end,GetSaveFolderPath=function()return '/private/save' end}}
package.loadlib=function()return function()return {open=function()return net end}end end
X4LAN_CONFIG={authority_world_bridge=true,authority_recovery_probe=true,test_profile='45841',
 authority_load_save_path='/private/save',authority_control_port=1234,
 authority_control_lease=string.rep('a',32),authority_world_epoch=string.rep('b',32),authority_marker_required=true}
SetScript=function(name,fn)assert(name=='onUpdate');callbacks=callbacks+1;update=fn end
DebugError=function(s)messages[#messages+1]=s end
RegisterEvent=function()end
GetSaveList=function(filter)if filter.save_008 then return {{filename='save_008'}} end return {} end
LoadGame=function(slot)assert(slot=='save_008');loads=loads+1;menu=false;valid=true end
Pause=function()paused=true end
X4LAN_AUTHORITY_MARKER_READY=function()return true end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {} end,register_save_event=function()return true end}
X4LAN_AUTHORITY_LOCAL_CONTROL_BRIDGE={new=function()return {update=function()return true end}end}
GetCurRealTime=function()return now end
assert(loadfile(recovery))();assert(callbacks==0)
assert(loadfile(bridge))();assert(callbacks==1)
update();update();assert(loads==1 and #messages==1 and #sent==0)
-- Loading rebuilds UI; on the new UI the recovered player is already valid.
callbacks=0;assert(loadfile(recovery))();assert(loadfile(bridge))();assert(callbacks==1)
update();update();assert(paused and #sent==0)
update();assert(messages[2]=='[X4LAN] AUTH_RECOVERY PAUSED' and #sent==0)
now=4;update();assert(#sent==1 and sent[1]:match('^RECOVERY_READY|'))
assert(loads==1)
