local ffi=require('ffi');ffi.cdef[[void TestPause(bool);void TestGame(double);void TestSlot(int);]]
local mode=arg[1];local epoch,nonce=('a'):rep(32),('b'):rep(32)
X4LAN_CONFIG={authority_frame_enabled=true,authority_frame_epoch=epoch,authority_frame_nonce=nonce,
 authority_load_save_path='/private/45841/save'}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local events,logs,issued={}, {},nil;local marker=true;local slot=1
function RegisterEvent(name,callback)assert(not events[name]);events[name]=callback;return true end
function AddUITriggeredEvent(screen,op,args)
 assert(screen=='X4AuthorityFixtureFrameRead' and op=='Read' and not issued);issued=args;return true
end
function X4LAN_AUTHORITY_MARKER_READY()return marker end
function ConvertStringToLuaID(value)return tonumber(value)end
function ConvertIDTo64Bit(value)return value end
function GetComponentData(ref,a,b)
 assert(a=='macro' and b=='owner')
 if mode=='reentrant' then events['X4AuthorityFixtureFrameRead.Done'](nil,nonce..slot..'|0')end
 if ref==41 then return 'ship_arg_s_fighter_01_a_macro','player' end
 if slot==1 then return ref==53 and 'station_xen_shipyard_base_01_macro' or 'xenon_small_station_01_macro','xenon' end
 return ref==53 and 'landmarks_kha_hive_03_macro' or 'landmarks_kha_weaponplatform_01_macro','khaak'
end
function GetCurRealTime()return 1 end
function DebugError(value)logs[#logs+1]=value end
dofile('tools/dev/authority_fixture_frame_read.lua')
local function trigger()
 X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
 assert(issued and issued.request_id==nonce..slot and issued.epoch==epoch and issued.slot==slot)
 issued=nil
end
local function row(kind,actor,code,macro,owner)
 events['X4AuthorityFixtureFrameRead.Result'](nil,table.concat({nonce..slot,kind,actor,'0x2b',code,macro,owner},'|'))
end
trigger()
if mode=='paused' then ffi.C.TestPause(false) end
if mode=='clock' then ffi.C.TestGame(11) end
if mode=='marker' then marker=false end
row('ship','0x29','SHP-001','ship_arg_s_fighter_01_a_macro','player')
if mode=='paused' or mode=='clock' or mode=='marker' or mode=='reentrant' then
 assert(logs[#logs]:find(' ERROR ',1,true));return
end
for _,code in ipairs({'SLS-778','MRY-123','MYO-569'}) do
 local index=_;local macro=index==3 and 'station_xen_shipyard_base_01_macro' or 'xenon_small_station_01_macro'
 row('station',string.format('0x%x',50+index),code,macro,'xenon')
end
if mode=='duplicate' then
 row('station','0x33','SLS-778','xenon_small_station_01_macro','xenon')
 assert(logs[#logs]:find(' ERROR ',1,true));return
end
if mode=='bad_done' then
 events['X4AuthorityFixtureFrameRead.Done'](nil,nonce..'1|2')
 assert(logs[#logs]:find(' ERROR ',1,true));return
end
events['X4AuthorityFixtureFrameRead.Done'](nil,nonce..'1|3')
slot=2;ffi.C.TestSlot(2);trigger()
row('ship','0x29','SHP-001','ship_arg_s_fighter_01_a_macro','player')
for index,code in ipairs({'FPJ-079','OSK-110','JFP-464'}) do
 local macro=index==3 and 'landmarks_kha_hive_03_macro' or 'landmarks_kha_weaponplatform_01_macro'
 row('station',string.format('0x%x',50+index),code,macro,'khaak')
end
events['X4AuthorityFixtureFrameRead.Done'](nil,nonce..'2|3')
assert(#logs==10 and logs[10]=='[X4LAN] AUTH_FIXTURE_FRAME_READ DONE '..nonce..' 2 3 10')
for _,value in ipairs(logs)do assert(not value:find('0x',1,true))end
assert(X4LAN_FIXTURE_FRAME_READ_DONE())
for _,value in ipairs(logs)do print(value)end
ffi.C.TestPause(false);X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
assert(logs[#logs]:find(' ERROR ',1,true))
