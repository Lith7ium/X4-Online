-- Execute the installed Windows load/registry scripts with a simulated engine.
local folder, mode = assert(arg[1]), assert(arg[2])
local menu, valid, paused = true, false, false
local marker_ready, identity_ready = false, false
local frame, event_handler, request
local logs, pause_calls = {}, 0
package.preload.ffi = function()
 return {NULL={}, cdef=function()end, string=function(value)return value end,
  C={GetSaveFolderPath=function()return 'C:/private/45841/save/' end}}
end
DebugError = function(value) logs[#logs+1] = value end
GetCurRealTime = function()return 1 end
SetScript = function(name, callback)assert(name=='onUpdate');frame=callback end
RegisterEvent = function(name, callback)
 assert(name=='X4AuthorityShipRegistry.Correlated' and not event_handler)
 event_handler=callback;return true
end
AddUITriggeredEvent = function(screen, operation, arguments)
 assert(screen=='X4AuthorityShipRegistry' and operation=='Status' and not request)
 request=arguments.request_id;return true
end
X4LAN_AUTHORITY_MARKER_READY = function()return marker_ready end
X4LAN_IDENTITY_READY = function()return identity_ready end
X4LAN_AUTHORITY_X4_CLIENT_LOAD_ENGINE = {new=function()
 return {in_startmenu=function()return menu end, refresh=function()end,
  save_available=function()return true end, load=function()end,
  player_valid=function()return valid end, is_paused=function()return paused end,
  pause=function()pause_calls=pause_calls+1 end}
end}
dofile(folder..'/config.lua')
dofile(folder..'/client_load_barrier.lua')
dofile(folder..'/recovery_registry_status.lua')
dofile(folder..'/authority_download_load_probe.lua')
frame();frame()
assert(#logs==1 and logs[1]:find('load_requested|',1,true))
menu=false;valid=true
dofile(folder..'/authority_download_load_probe.lua') -- UI reset after load.
frame();frame();assert(not request and pause_calls==0)
marker_ready=true
frame();assert(not request and pause_calls==0)
identity_ready=true
frame();frame();assert(pause_calls==1 and not request and #logs==1)
paused=true
frame();frame();assert(request and event_handler and #logs==1)
event_handler(nil,request..'|Epoch|'..string.rep('1',32))
if mode=='ready' then
 event_handler(nil,request..'|Count|3')
 assert(#logs==2 and logs[2]:find('AUTH_RECOVERY_REGISTRY ',1,true))
 frame()
 assert(#logs==3 and logs[3]:find('pause_observed|',1,true))
elseif mode=='wrong_count' then
 assert(not pcall(event_handler,nil,request..'|Count|4'))
 frame()
 for _,line in ipairs(logs)do assert(not line:find('pause_observed|',1,true))end
 assert(logs[2]:find('AUTH_RECOVERY_REGISTRY_ERROR ',1,true))
else error('unknown test mode')end
