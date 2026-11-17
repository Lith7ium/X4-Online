-- Synthetic C ABI; validates the private recovery update owner without X4.
local ffi=require('ffi');ffi.load(assert(arg[1]),true)
local events,logs,requests={},{},{}
function RegisterEvent(name,fn) assert(not events[name]);events[name]=fn end
function DebugError(value) logs[#logs+1]=value end
local now=1
function GetCurRealTime() return now end
function AddUITriggeredEvent(screen,control,values)
 requests[#requests+1]={screen,control,values};return true
end
local nonce,epoch=string.rep('a',32),string.rep('b',32)
X4LAN_CONFIG={authority_saved_registry_verify=true,authority_saved_registry_nonce=nonce,
 authority_fixture_epoch=epoch,authority_saved_registry_timeout=20,authority_load_save_path='/tmp/45841/save'}
dofile('tools/dev/authority_saved_registry_verify_owner.lua')
local event=events['X4AuthoritySavedRegistryVerify.Matched']
if arg[2]=='early' then
 event(nil,nonce..'|'..epoch..'|4|3|4')
 assert(not pcall(X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK));return
end
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
assert(#requests==1 and requests[1][1]=='X4AuthoritySavedRegistryVerify' and requests[1][2]=='Read')
if arg[2]=='bad_nonce' then
 event(nil,string.rep('c',32)..'|'..epoch..'|4|3|4')
 assert(not pcall(X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK));return
end
event(nil,nonce..'|'..epoch..'|4|3|4')
if arg[2]=='timeout' then
 now=100
 assert(not pcall(X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK))
 for _,line in ipairs(logs) do assert(not line:match(' MATCHED 4 3 4$')) end
 return
end
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
assert(logs[#logs]=='[X4LAN] AUTH_SAVED_REGISTRY_VERIFY MATCHED 4 3 4')
event(nil,nonce..'|'..epoch..'|4|3|4')
assert(not pcall(X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK))
