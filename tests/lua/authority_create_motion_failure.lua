-- Fake X4 UI events; ensure a failure fences the outstanding guard callback.
local callbacks,update={},nil
local epoch,lease=string.rep('a',32),string.rep('b',32)
local actor={};local command='CMD|'..lease..'|SPAWN';local fleet=1
local stopped,closed,written=0,0,0
X4LAN_CONFIG={authority_create_role='server',authority_create_epoch=epoch,
 authority_create_lease=lease,authority_create_port=12345,authority_motion_test=true,
 authority_motion_port=12346,authority_motion_lease=string.rep('c',32),authority_motion_save_path='/tmp/45841/save'}
package.loaded.ffi={C={IsPlayerValid=function() return true end,IsGamePaused=function() return true end},
 cdef=function() end,new=function(_,value) return value end}
function RegisterEvent(n,cb) callbacks[n]=cb end
function SetScript(_,cb) update=cb end
function DebugError(_) end
function GetCurRealTime() return 1 end
function ConvertIDTo64Bit(v) assert(v==actor);return 123 end
function ConvertStringToLuaID(v) return v end
function GetComponentData(_,_) return 'ship_arg_s_fighter_01_a_macro' end
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {fleet_count=function() return fleet end,
 fleet=function(_,n) local t={};for i=1,fleet do t[i]=i end;return t,false end,
 operational=function() return true end,is_ship=function() return true end,key=function(v) return tostring(v) end} end}
local control={send=function() return true end,receive=function() local c=command;command=nil;return c end}
local data={close=function() closed=closed+1 end}
local opens=0
package.loadlib=function() return function() return {open=function() opens=opens+1;return opens==1 and control or data end,monotonic=function() return 1 end} end end
X4LAN_AUTHORITY_REGISTRY_MOTION={};X4LAN_AUTHORITY_FIXTURE_WIRE={};X4LAN_AUTHORITY_FIXTURE_CONTINUOUS={}
X4LAN_AUTHORITY_REGISTRY_MOTION_NATIVE={new=function() return {tick=function() end,stop=function() stopped=stopped+1 end,
 verified=function() written=written+1 end,refused=function() end} end}
local function event(name,value) assert(callbacks[name]);callbacks[name](nil,value) end
function AddUITriggeredEvent(screen,op,args)
 if op=='Initialize' then event(screen..'.Initialized',epoch)
 elseif op=='Spawn' then
  event(screen..'.Ship',actor);event(screen..'.SectorId','cluster_01')
  for k,v in pairs({Macro='ship_arg_s_fighter_01_a_macro',Owner='argon',Seed=7183,X=-400,Y=100000,Z=500}) do event(screen..'.'..k,v) end
  fleet=2;event(screen..'.Spawned')
 elseif op=='Enroll' then event(screen..'.Enrolled',1)
 else error('unexpected '..op) end
end
assert(loadfile('tools/dev/authority_create_test_probe.lua'))()
assert(X4LAN_AUTHORITY_CREATE_READY());update()
command='CMD|'..lease..'|MOTION';update()
command='CMD|'..lease..'|BAD';update() -- triggers fail() while guard event is pending
assert(stopped==1 and closed==1)
event('X4AuthorityRegistryMotionGuard.Verified',actor)
event('X4AuthorityRegistryMotionGuard.Refused')
assert(written==0 and stopped==1 and closed==1)
print('late guard response fenced after failure')
