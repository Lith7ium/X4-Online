-- Synthetic player API and event responses; this does not load X4.
local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
ffi.cdef[[void TestMove(void);void TestRogue(void);]]
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local events,requests,logs={},{},{}
function RegisterEvent(name,fn) assert(not events[name]);events[name]=fn end
function DebugError(value)
 logs[#logs+1]=value
 if arg[3]=='post_done_fault' and value:match(' DONE$') then fake.TestRogue() end
end
function GetCurRealTime() return 1 end
function AddUITriggeredEvent(screen,operation,args) requests[#requests+1]={screen,operation,args} end
function ConvertStringToLuaID(value)
 local id=ffi.new('uint64_t',0);for digit in value:gmatch('%d') do id=id*10+tonumber(digit) end;return id
end
function ConvertIDTo64Bit(value) return ffi.new('uint64_t',value) end
function GetComponentData(_,first,second,third)
 if first=='owner' then return 'player' end
 assert(first=='isdocked' and second=='isdocking' and third=='isinternallystored')
 return false,false,false
end
X4LAN_CONFIG={authority_saved_player_control=true,authority_fixture_timeout=20,authority_fixture_nonce=nonce,
 authority_fixture_epoch=epoch,authority_fixture_slot=2,authority_load_save_path='/tmp/45841/save'}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
dofile(assert(arg[2]));dofile('tools/dev/authority_player_control_live_owner.lua')
dofile('tools/dev/authority_saved_player_control_owner.lua')
local function send(name,value) events['X4AuthorityPlayerControlOnce.'..name](nil,value) end
local function row(sequence,flags) return nonce..'|'..epoch..'|'..sequence..'|0x20000000000001|0xb|'..flags..'|1|player' end
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
assert(requests[#requests][2]=='Create' and requests[#requests][3].slot==2)
if arg[3]=='bad_nonce' then
 send('Created',string.rep('c',32)..'|'..epoch..'|0x20000000000001|0xb')
 assert(logs[#logs]:match(' ERROR FAULT$'));return
end
send('Created',nonce..'|'..epoch..'|0x20000000000001|0xb')
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK();send('ReadResult',row(0,'0|0|0|1'))
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK();assert(requests[#requests][2]=='Teleport')
if arg[3]=='rogue' then
 fake.TestRogue();send('Dispatched',nonce..'|'..epoch)
 assert(logs[#logs]:match(' ERROR FAULT$'));return
end
fake.TestMove();send('Dispatched',nonce..'|'..epoch)
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK();send('ReadResult',row(1,'1|1|1|1'))
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK();send('ReadResult',row(2,'1|1|1|1'))
if arg[3]=='post_done_fault' then
 assert(not pcall(X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK))
 assert(logs[#logs]:match(' ERROR FAULT$'))
 for _,line in ipairs(logs) do assert(not line:match(' FENCED$')) end
 return
end
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
assert(logs[#logs-2]:match(' CONTROLLED$') and logs[#logs-1]:match(' DONE$') and logs[#logs]:match(' FENCED$'))
