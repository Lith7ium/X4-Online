-- Synthetic local callbacks; no X4 or native FFI.
local mode=arg[1];local callbacks={};local queue={};local logs={};local epoch=string.rep('a',32)
local paused=true
X4LAN_CONFIG={authority_resolve_v2_native=true,authority_resolve_epoch=epoch,authority_resolve_id1=string.rep('b',32),
 authority_resolve_id2=string.rep('c',32),authority_resolve_save_path='/private/45841/save'}
package.loaded.ffi={C={IsGamePaused=function() return paused end,GetSaveFolderPath=function() return '/private/45841/save' end,
 IsValidComponent=function() return true end,IsComponentOperational=function() return true end,
 IsComponentClass=function() return true end},NULL={},cdef=function() end,typeof=function() return true end,
 string=function(v) return v end,new=function(_,v) return v end}
function RegisterEvent(n,f) assert(not callbacks[n]);callbacks[n]=f end
function AddUITriggeredEvent(screen,control,args)
 if mode=='dispatch-false' then return false end
 queue[#queue+1]={screen,control,args}
end
function ConvertIDTo64Bit(v) return v end
function ConvertStringToLuaID(v) return tonumber(v) end
function DebugError(s) logs[#logs+1]=s end
function GetCurRealTime() return 1 end
function Pause() error('unexpected pause') end
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {
 factions=function() return {'argon'},false end,fleet_count=function() return 1 end,
 fleet=function() return {42},false end,operational=function() return true end,
 is_ship=function() return true end,key=function() return '42ULL' end} end}
assert(loadfile('tools/dev/authority_registry_resolve_v2.lua'))()
assert(type(X4LAN_RESOLVE_V2)=='table')
assert(loadfile('tools/dev/authority_registry_resolve_v2_native.lua'))()
local function event(name,value) assert(callbacks[name]);callbacks[name](nil,value) end
if mode=='dispatch-false' then
 assert(not pcall(X4LAN_RESOLVE_V2_NATIVE_READY));assert(logs[#logs]:find('ERROR dispatch',1,true));return
end
assert(not X4LAN_RESOLVE_V2_NATIVE_READY())
while #queue>0 do
 local request=table.remove(queue,1);local s,op,args=unpack(request)
 if mode=='pause-loss' then paused=false;assert(not pcall(event,s..'.Initialized',epoch));break end
 if s=='X4AuthorityShipRegistry' and op=='Initialize' then event(s..'.Initialized',epoch)
 elseif s=='X4AuthorityShipRegistry' and op=='Enroll' then assert(args.ship==42);event(s..'.Enrolled',1)
 elseif s=='X4AuthorityRegistryResolveV2' and op=='Resolve' then
  if mode=='invalid-table' then event(s..'.Result','not a table');break end
  local row={request_id=args.request_id,epoch=epoch,index=args.index,status=args.index==1 and 'ok' or 'unavailable'}
  if args.index==1 then row.actor=42 end
  event(s..'.Result',row)
 else error('unexpected request') end
end
if mode=='ok' then assert(X4LAN_RESOLVE_V2_NATIVE_READY());assert(logs[#logs]:find('DONE',1,true))
else assert(not pcall(X4LAN_RESOLVE_V2_NATIVE_READY)) end
print('native ResolveV2 synthetic '..mode..' passed')
