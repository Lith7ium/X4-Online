-- Isolated LuaJIT driver: no X4, native bindings, network, or files are opened.
local callbacks, onupdate, enrolled, converted = {}, nil, nil, {}
local epoch=string.rep('a',32)
local lease=string.rep('b',32)
local actor={kind='event-object'}
local invalid_macro=arg[1]=='invalid-macro'
local command='CMD|'..lease..'|SPAWN'
X4LAN_CONFIG={authority_create_role='server',authority_create_epoch=epoch,
 authority_create_lease=lease,authority_create_port=12345}
package.loaded.ffi={C={IsPlayerValid=function() return true end,IsGamePaused=function() return true end},cdef=function() end}
function RegisterEvent(name,callback) assert(not callbacks[name]);callbacks[name]=callback end
function SetScript(name,callback) assert(name=='onUpdate');onupdate=callback end
function DebugError(message) if message:find(' ERROR ',1,true) then error(message) end end
function GetCurRealTime() return 1 end
function Pause() error('unexpected pause') end
function ConvertIDTo64Bit(value) assert(value==actor);return '123ULL' end
function ConvertStringToLuaID(...)
 assert(select('#',...)==1,'converter received more than one argument')
 local value=...;assert(type(value)=='string' and value:match('^%d+$'))
 converted[#converted+1]=value;return 'local-id:'..value
end
function GetComponentData(id,field)
 assert(id=='local-id:42' and field=='macro')
 if invalid_macro then return nil end
 return 'ship_arg_s_fighter_01_a_macro'
end
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {
 fleet_count=function(faction) assert(faction=='argon');return 1 end,
 fleet=function(faction,capacity) assert(faction=='argon' and capacity==2);return {42},false end,
 operational=function(value) assert(value==42);return true end,
 is_ship=function(value) assert(value==42);return true end,
 key=function(value) assert(value==42);return '42ULL' end,
} end}
local net={send=function(_,_) return true end,receive=function() local result=command;command=nil;return result end}
package.loadlib=function(_,name) assert(name=='luaopen_x4lan_net');return function() return {open=function() return net end} end end
local function event(name,value) assert(callbacks[name],name);callbacks[name](nil,value) end
function AddUITriggeredEvent(screen,control,args)
 if screen=='X4AuthorityShipRegistry' and control=='Initialize' then
  assert(args.epoch==epoch);event(screen..'.Initialized',epoch)
 elseif screen=='X4AuthorityShipCreateReceiver' and control=='Initialize' then
  assert(args.epoch==epoch);event(screen..'.Initialized',epoch)
 elseif screen=='X4AuthorityCreateFixture' and control=='Spawn' then
  event(screen..'.Ship',actor);event(screen..'.SectorId','cluster_01')
  event(screen..'.Macro','ship_arg_s_fighter_01_a_macro');event(screen..'.Owner','argon')
  event(screen..'.Seed',7183);event(screen..'.X',-400);event(screen..'.Y',100000);event(screen..'.Z',500)
  event(screen..'.Spawned')
 elseif screen=='X4AuthorityShipRegistry' and control=='Enroll' then
  assert(args.epoch==epoch);enrolled=args.ship
 else error('unexpected event '..screen..'.'..control) end
end
assert(loadfile('tools/dev/authority_create_test_probe.lua'))()
assert(not callbacks['X4AuthorityRegistryMotionGuard.Verified'] and not callbacks['X4AuthorityRegistryMotionGuard.Refused'], 'default path registered motion handlers')
assert(X4LAN_AUTHORITY_CREATE_READY())
assert(onupdate)
if invalid_macro then
 local ok,err=pcall(onupdate)
 assert(not ok and tostring(err):find('invalid fleet macro',1,true),'invalid macro was not refused')
 assert(enrolled==nil,'invalid macro must prevent enrollment')
 print('invalid fleet macro refused')
 return
end
onupdate()
assert(enrolled=='local-id:123','actor must be normalized before Enroll')
assert(#converted==2 and converted[1]=='42' and converted[2]=='123','unexpected conversion inputs')
print('single-argument conversion and event actor enrollment passed')
