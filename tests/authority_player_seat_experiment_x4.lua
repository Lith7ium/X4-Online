-- Fake X4 ABI and callbacks: integration of the real owner and seat adapter only.
local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
ffi.cdef[[double GetCurrentGameTime(void);]]
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local events,requests,logs={},{},{}
function RegisterEvent(name,fn) assert(not events[name]);events[name]=fn end
function DebugError(value) logs[#logs+1]=value end
function AddUITriggeredEvent(screen,op,args) requests[#requests+1]={screen,op,args} end
function ConvertStringToLuaID(value) return ffi.new('uint64_t',tonumber(value)) end
function ConvertIDTo64Bit(value) return ffi.new('uint64_t',value) end
function GetCurRealTime() return 1 end
function GetComponentData(id,field)
 if field=='hullpercent' then return 100 end
 if field=='assignedpilot' then if tonumber(id)==10 then return ffi.new('uint64_t',99) end;return nil end
 error('invalid getter')
end
function X4LAN_SECTOR_READ_EXPORT() return ffi.new('uint64_t',10),ffi.new('uint64_t',11),2,3 end
X4LAN_CONFIG={authority_player_seat_experiment=true,authority_sector_epoch=epoch,
 authority_player_seat_nonce=nonce,authority_player_seat_timeout=10,authority_read_save_path='/tmp/45841/save'}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
dofile('tools/dev/authority_player_seat_calibration.lua')
dofile('tools/dev/authority_player_seat_experiment.lua')
local function send(name,value) assert(events[name]);events[name](nil,value) end
local function row(slot,actor,sector,reservation)
 return nonce..'-'..slot..'|'..epoch..'|'..slot..'|'..actor..'|'..sector..'|'..reservation
end
X4LAN_PLAYER_SEAT_EXPERIMENT_TICK();assert(requests[1][2]=='Preflight')
send('X4AuthorityPlayerSeatExperiment.Preflight',nonce..'|'..epoch..'|ok')
X4LAN_PLAYER_SEAT_EXPERIMENT_TICK();assert(requests[2][2]=='Create')
send('X4AuthorityPlayerSectorFixture.Created',2);X4LAN_PLAYER_SEAT_EXPERIMENT_TICK()
assert(requests[3][3].slot==0)
send('X4AuthorityPlayerSeatCalibration.Result',row(0,'0xa','0xb','occupied'))
send('X4AuthorityPlayerSeatCalibration.Result',row(1,'0xc','0xd','empty'))
send('X4AuthorityPlayerSeatCalibration.Result',row(2,'0xe','0xb','empty'))
X4LAN_PLAYER_SEAT_EXPERIMENT_TICK();assert(logs[#logs]:match(' DONE$'))
send('X4AuthorityPlayerSeatCalibration.Result',row(2,'0xe','0xb','empty'))
assert(logs[#logs]:match(' ERROR FAULT$'));assert(not pcall(X4LAN_PLAYER_SEAT_EXPERIMENT_TICK))
