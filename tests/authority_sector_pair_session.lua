-- Offline session -> real UDP adapter -> real X4 adapter -> driver wiring.
local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
local epoch=string.rep('a',32);local attempt=string.rep('b',32);local nonce=string.rep('c',32);local lease=string.rep('d',32)
local sent,handlers,queue,ui={},{},{},{}
function RegisterEvent(name,callback)assert(not handlers[name]);handlers[name]=callback end
function AddUITriggeredEvent(screen,op,args)ui[#ui+1]={screen,op,args};return true end
function GetCurRealTime()return 1 end
function ConvertStringToLuaID(v)return ffi.new('uint64_t',tonumber(v)) end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v) end
function GetComponentData()return 'ship_arg_s_fighter_01_a_macro' end
function DebugError()end
function X4LAN_SECTOR_PAIR_TICK()return true end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_AUTHORITY_SHIP_ENGINE={new=function()return {fleet_count=function()return 0 end,fleet=function(_,cap)assert(cap==1);return {},false end}end}
X4LAN_PAIR_CREATE_DRIVER=dofile('tools/dev/authority_sector_pair_create.lua')
X4LAN_PAIR_CREATE_X4=dofile('tools/dev/authority_sector_pair_create_x4.lua')
X4LAN_PAIR_CREATE_UDP=dofile('tools/dev/authority_sector_pair_create_udp.lua')
local net={send=function(_,value)sent[#sent+1]=value;return true end,
 receive=function()return table.remove(queue,1)end,close=function()return true end}
package.loadlib=function()return function()return {open=function(host,port)assert(host=='127.0.0.1' and port==5000);return net end}end end
X4LAN_CONFIG={authority_pair_create=true,authority_pair_role='server',authority_pair_lease=lease,
 authority_pair_attempt=attempt,authority_sector_epoch=epoch,authority_pair_nonce=nonce,
 authority_pair_macros={'sector_one','sector_two'},authority_pair_deadline=600,
 authority_pair_port=5000,authority_read_save_path='/tmp/45841/save'}
dofile('tools/dev/authority_sector_pair_session.lua')
X4LAN_PAIR_CREATE_TICK()
assert(sent[1]=='PAIR|'..lease..'|server|'..attempt..'|'..epoch..'|READY')
queue[1]='CMD|'..lease..'|server|'..attempt..'|'..epoch..'|START'
X4LAN_PAIR_CREATE_TICK()
assert(#ui==1 and ui[1][1]=='X4AuthorityShipCreateReceiver' and ui[1][2]=='Initialize' and ui[1][3].epoch==epoch)
assert(handlers['X4AuthorityShipCreateReceiver.Initialized'])
