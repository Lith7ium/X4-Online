-- Synthetic local test: a server-described ship enters the Lua-to-MD request.
local callbacks, onupdate, submitted, error_log={},nil,nil,nil
local variant=arg[1] or 'success'
local lease=string.rep('b',32)
X4LAN_CONFIG={authority_create_role='client',authority_create_epoch=string.rep('a',32),
 authority_create_lease=lease,authority_create_port=12345}
package.loaded.ffi={C={IsPlayerValid=function() return true end,IsGamePaused=function() return true end},cdef=function() end}
function RegisterEvent(name,callback) callbacks[name]=callback end
function SetScript(_,callback) onupdate=callback end
function DebugError(message) if message:find(' ERROR ',1,true) then error_log=message end end
function GetCurRealTime() return 1 end
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {
 fleet_count=function() return 0 end, fleet=function(_,capacity) assert(capacity==1);return {},false end,
} end}
local command='CMD|'..lease..'|CREATE|ship_arg_s_fighter_01_a_macro|cluster_01|argon|7183|-400|100000|500'
local net={send=function() return true end,receive=function() local value=command;command=nil;return value end}
package.loadlib=function() return function() return {open=function() return net end} end end
local function event(name,value) assert(callbacks[name]);callbacks[name](nil,value) end
function AddUITriggeredEvent(screen,control,args)
 if screen=='X4AuthorityCreateFixture' and control=='Descriptor' then
  event(screen..'.SectorId',variant=='sector-mismatch' and 'cluster_other' or 'cluster_01')
  event(screen..'.Described')
 elseif screen=='X4AuthorityShipCreateReceiver' and control=='Create' then submitted=args
 else error('unexpected event '..screen..'.'..control) end
end
assert(loadfile('tools/dev/authority_create_test_probe.lua'))()
assert(onupdate)
if variant=='sector-mismatch' then
 onupdate()
 assert(error_log and error_log:find('descriptor_sector',1,true),'sector mismatch was not refused')
 assert(submitted==nil,'sector mismatch must prevent Create')
 print('mismatched sector refused');return
end
onupdate()
assert(submitted and submitted.epoch==string.rep('a',32) and submitted.index==1)
assert(submitted.macro=='ship_arg_s_fighter_01_a_macro' and submitted.sector=='cluster_01' and submitted.owner=='argon')
assert(submitted.seed==7183 and submitted.x==-400 and submitted.y==100000 and submitted.z==500)
print('received string IDs and metre numbers passed to MD Create')
