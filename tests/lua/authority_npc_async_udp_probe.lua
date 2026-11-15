-- Source UI/MD event timing simulation with the real loopback UDP native module.
-- Does not launch X4; the C symbols are supplied by a test library.
local ffi=require('ffi');ffi.cdef[[void test_state(bool,float,double); int usleep(unsigned int);]]
local fake=ffi.load(assert(arg[1]),true);local network_path=assert(arg[2])
local port=assert(tonumber(arg[3]));local lease=assert(arg[4]);local epoch=string.rep('a',32)
local callbacks,update,queue={},nil,{}
X4LAN_CONFIG={authority_npc_flight_source=true,test_profile='45841',authority_create_epoch=epoch,
 authority_npc_lease=lease,authority_npc_port=port,authority_motion_port=port,
 authority_motion_lease=string.rep('c',32),authority_motion_save_path='/tmp/45841/save'}
function RegisterEvent(n,cb) callbacks[n]=cb end
function SetScript(_,cb) update=cb end
function DebugError(line) print(line) end
function ConvertIDTo64Bit(v) return v end
function ConvertStringToLuaID(v) return v end
function GetComponentData() return false,false,false end
local loadlib=package.loadlib
package.loadlib=function(_,name) return loadlib(network_path,name) end
local function event(name,v) assert(callbacks[name]);callbacks[name](nil,v) end
function AddUITriggeredEvent(screen,op,_)
 assert(screen=='X4AuthorityNPCFlightFixture' and op=='Order')
 -- Queue until after the current UI update returns, like an asynchronous MD
 -- event. The immediate-callback unit test does not cover this ordering.
 queue[#queue+1]=function()
  event(screen..'.Pilot',99);event(screen..'.OrderId','MoveWait');event(screen..'.GameTime',0);event(screen..'.Ready',1)
 end
end
fake.test_state(true,0,0)
assert(loadfile('tools/dev/authority_npc_flight_source.lua'))()
for _=1,500 do
 update()
 local current=queue;queue={};for _,fn in ipairs(current) do fn() end
 ffi.C.usleep(5000)
end
