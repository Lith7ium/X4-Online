local ffi=require('ffi');ffi.cdef[[void TestPause(bool);void TestGame(double);]]
local mode=arg[1];local epoch,nonce=('a'):rep(32),('b'):rep(32)
X4LAN_CONFIG={authority_frame_enabled=true,authority_frame_epoch=epoch,authority_frame_nonce=nonce,
 authority_frame_ship_index=1318,authority_frame_sector='cluster_115_sector001_macro',authority_load_save_path='/private/45841/save'}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local events,logs,issued={}, {},nil;local marker=true
function RegisterEvent(name,callback)assert(not events[name]);events[name]=callback;return true end
function AddUITriggeredEvent(screen,op,args)assert(screen=='X4AuthorityFrameRead' and op=='Read' and not issued);issued=args;return true end
function X4LAN_AUTHORITY_MARKER_READY()return marker end
function ConvertStringToLuaID(x)return tonumber(x)end
function ConvertIDTo64Bit(x)return x end
function GetComponentData(ref,a,b)
 assert(a=='macro' and b=='owner')
 if mode=='reentrant' then events['X4AuthorityFrameRead.Done'](nil,nonce..'|0')end
 return ref==41 and 'ship_a' or 'station_gen_factory_base_01_macro','pioneers'
end
function GetCurRealTime()return 1 end
function DebugError(s)logs[#logs+1]=s end
dofile('tools/dev/authority_frame_read.lua');X4LAN_FRAME_READ_TICK()
assert(issued and issued.request_id==nonce and issued.epoch==epoch and issued.index==1318)
local function row(kind,actor,code,macro,owner)
 events['X4AuthorityFrameRead.Result'](nil,table.concat({nonce,kind,actor,'0x2b',code,macro,owner},'|'))
end
if mode=='paused' then ffi.C.TestPause(false)end
if mode=='clock' then ffi.C.TestGame(11)end
if mode=='marker' then marker=false end
row('ship','0x29','SHP-001','ship_a','pioneers')
if mode=='paused' or mode=='clock' or mode=='marker' or mode=='reentrant' then assert(logs[#logs]:find(' ERROR ',1,true));return end
row('station','0x33','AAJ-808','station_gen_factory_base_01_macro','pioneers')
if mode=='duplicate' then row('station','0x33','AAJ-808','station_gen_factory_base_01_macro','pioneers')
elseif mode=='wrongcode' then row('station','0x34','RZT-476','station_gen_factory_base_01_macro','pioneers')
elseif mode=='wrongmacro' then row('station','0x34','UKN-243','station_gen_factory_base_01_macro','argon')
else
 row('station','0x34','UKN-243','station_gen_factory_base_01_macro','pioneers')
 row('station','0x35','RZT-476','station_gen_factory_base_01_macro','pioneers')
end
if mode=='duplicate' or mode=='wrongcode' or mode=='wrongmacro' then assert(logs[#logs]:find(' ERROR ',1,true));return end
if mode=='bad_done' then events['X4AuthorityFrameRead.Done'](nil,nonce..'|2');assert(logs[#logs]:find(' ERROR ',1,true));return end
events['X4AuthorityFrameRead.Done'](nil,nonce..'|3')
assert(#logs==5 and logs[5]=='[X4LAN] AUTH_FRAME_READ DONE '..nonce..' 3 10')
for _,v in ipairs(logs)do assert(not v:find('0x',1,true))end
X4LAN_FRAME_READ_TICK();assert(#logs==5)
ffi.C.TestPause(false);X4LAN_FRAME_READ_TICK();assert(logs[#logs]:find(' ERROR ',1,true))
