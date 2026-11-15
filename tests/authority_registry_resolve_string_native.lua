-- Synthetic callbacks only; LuaJIT uint64 arithmetic is real, X4 bindings are faked.
local real=require('ffi');local mode=arg[1];local handlers={};local queue={};local logs={};local paused=true
local epoch=string.rep('a',32)
local high=real.new('uint64_t',9007199254740992)+real.new('uint64_t',1)
X4LAN_CONFIG={authority_resolve_string_native=true,authority_resolve_epoch=epoch,authority_resolve_id1=string.rep('b',32),
 authority_resolve_id2=string.rep('c',32),authority_resolve_save_path='/private/45841/save'}
package.loaded.ffi={C={IsGamePaused=function() return paused end,GetSaveFolderPath=function() return '/private/45841/save' end,
 IsValidComponent=function() return true end,IsComponentOperational=function() return true end,IsComponentClass=function() return true end},
 NULL={},cdef=function() end,typeof=function() return true end,string=function(v) return v end,istype=real.istype,
 new=function(t,v) return real.new(t=='UniverseID' and 'uint64_t' or t,v) end}
function RegisterEvent(n,f) assert(not handlers[n]);handlers[n]=f end
function AddUITriggeredEvent(s,o,a) if mode=='dispatch-false' then return false end;queue[#queue+1]={s,o,a} end
function ConvertIDTo64Bit(v)
 if mode=='unsafe-number' then return 9007199254740992 end
 if mode=='high-cdata' then return high end
 if mode=='number-safe' then return tonumber(v) end
 return real.new('uint64_t',v)
end
function ConvertStringToLuaID(v) if mode=='high-cdata' or mode=='unsafe-number' then return 77 end;return tonumber(v) end
function DebugError(s) logs[#logs+1]=s end
function GetCurRealTime() return 1 end
function Pause() error('unexpected pause') end
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {factions=function() return {'argon'},false end,
 fleet_count=function() return 1 end,fleet=function() return {(mode=='high-cdata' or mode=='unsafe-number') and high or real.new('uint64_t',42)},false end,
 operational=function() return true end,is_ship=function() return true end,
 key=function(v) return tostring(v) end} end}
assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
assert(loadfile('tools/dev/authority_registry_resolve_string_native.lua'))()
local function event(name,v) assert(handlers[name]);handlers[name](nil,v) end
if mode=='dispatch-false' then assert(not pcall(X4LAN_RESOLVE_STRING_NATIVE_READY));return end
if mode=='unsafe-number' then assert(not pcall(X4LAN_RESOLVE_STRING_NATIVE_READY));return end
assert(not X4LAN_RESOLVE_STRING_NATIVE_READY())
while #queue>0 do
 local q=table.remove(queue,1);local s,op,a=unpack(q)
 if mode=='pause-loss' then paused=false;assert(not pcall(event,s..'.Initialized',epoch));break end
 if s=='X4AuthorityShipRegistry' and op=='Initialize' then event(s..'.Initialized',epoch)
 elseif s=='X4AuthorityShipRegistry' and op=='Enroll' then assert(a.ship==(mode=='high-cdata' and 77 or 42));event(s..'.Enrolled',1)
 elseif s=='X4AuthorityRegistryResolveString' and op=='Resolve' then
  local tail=a.index==1 and (mode=='actor-mismatch' and '0x2b' or (mode=='no-prefix' and '000002a' or (mode=='high-cdata' and '0x20000000000001' or '0x2a'))) or '0'
  local status=a.index==1 and 'ok' or 'unavailable'
  local request_id=mode=='bad-id' and string.rep('d',32) or a.request_id
  event(s..'.Result',request_id..'|'..epoch..'|'..a.index..'|'..status..'|'..tail)
  if mode=='actor-mismatch' or mode=='no-prefix' or mode=='bad-id' then break end
 else error('unexpected request') end
end
if mode=='ok' or mode=='number-safe' or mode=='high-cdata' then assert(X4LAN_RESOLVE_STRING_NATIVE_READY());assert(logs[#logs]:find('DONE',1,true))
else assert(not pcall(X4LAN_RESOLVE_STRING_NATIVE_READY)) end
local log=table.concat(logs,'\n')
if mode=='no-prefix' then
 assert(log:find('actor_format=hex actor_length=7 prefix=none',1,true))
 assert(log:find('reason=actor_hex expected_type=not_called',1,true))
elseif mode=='actor-mismatch' then assert(log:find('reason=actor_mismatch expected_type=fleet_uint64',1,true))
elseif mode=='bad-id' then
 assert(log:find('id_match=false',1,true));assert(log:find('reason=mismatch expected_type=not_called',1,true))
end
print('ResolveString native probe synthetic '..mode..' passed')
