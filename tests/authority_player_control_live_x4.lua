local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true);ffi.cdef[[void TestMove(void);void TestReset(void);void TestRogue(void);void TestDropNPC(void);]]
local epoch,nonce=string.rep('a',32),string.rep('b',32);local events,requests,logs={},{},{};local t=1
function RegisterEvent(n,f)assert(not events[n]);events[n]=f end
function DebugError(s)logs[#logs+1]=s end
function GetCurRealTime()return t end
function AddUITriggeredEvent(s,o,a)requests[#requests+1]={s,o,a}end
function ConvertStringToLuaID(s)local v=ffi.new('uint64_t',0);for d in s:gmatch('%d')do v=v*10+tonumber(d)end;return v end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v)end
function GetComponentData(_,a,b,c)if a=='owner'then return 'player'end;assert(a=='isdocked' and b=='isdocking' and c=='isinternallystored');return false,false,false end
function X4LAN_SECTOR_READ_EXPORT()return ffi.new('uint64_t',13),ffi.new('uint64_t',11),2,3 end
X4LAN_CONFIG={authority_player_control_live=true,authority_player_control_timeout=20,authority_player_control_nonce=nonce,
 authority_sector_epoch=epoch,authority_read_save_path='/tmp/45841/save'}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
dofile('tools/dev/authority_player_control_once.lua');dofile('tools/dev/authority_player_control_live_owner.lua')
local function send(n,v)events['X4AuthorityPlayerControlOnce.'..n](nil,v)end
local function row(seq,flags)return nonce..'|'..epoch..'|'..seq..'|0x20000000000001|0xb|'..flags..'|1|player'end
X4LAN_PLAYER_CONTROL_LIVE_TICK();assert(requests[#requests][2]=='Create')
if arg[2]=='timeout' then t=11;X4LAN_PLAYER_CONTROL_LIVE_TICK();X4LAN_PLAYER_CONTROL_LIVE_TICK();assert(logs[#logs-1]:match(' INCONCLUSIVE$'));send('Created',nonce..'|'..epoch..'|0x20000000000001|0xb');assert(logs[#logs]:match(' ERROR FAULT$'));return end
if arg[2]=='bad_nonce' then send('Created',string.rep('c',32)..'|'..epoch..'|0x20000000000001|0xb');assert(logs[#logs]:match(' ERROR FAULT$'));return end
send('Created',nonce..'|'..epoch..'|0x20000000000001|0xb');X4LAN_PLAYER_CONTROL_LIVE_TICK()
send('ReadResult',row(0,'0|0|0|1'));if arg[2]=='npc_lost' then fake.TestDropNPC();assert(not pcall(X4LAN_PLAYER_CONTROL_LIVE_TICK));assert(logs[#logs]:match(' ERROR FAULT$'));assert(requests[#requests][2]~='Teleport');return end;X4LAN_PLAYER_CONTROL_LIVE_TICK();assert(requests[#requests][2]=='Teleport')
if arg[2]=='rogue' then fake.TestRogue();send('Dispatched',nonce..'|'..epoch);assert(logs[#logs]:match(' ERROR FAULT$'));return end
if arg[2]~='inconclusive' then fake.TestMove() end
send('Dispatched',nonce..'|'..epoch);X4LAN_PLAYER_CONTROL_LIVE_TICK()
if arg[2]=='inconclusive'then
 send('ReadResult',row(1,'0|0|0|1'));X4LAN_PLAYER_CONTROL_LIVE_TICK();assert(logs[#logs-1]:match(' INCONCLUSIVE$'))
else
 send('ReadResult',row(1,'1|1|1|1'));if arg[2]=='relapse' then fake.TestReset();assert(not pcall(X4LAN_PLAYER_CONTROL_LIVE_TICK));assert(logs[#logs]:match(' ERROR FAULT$'));return end;X4LAN_PLAYER_CONTROL_LIVE_TICK();send('ReadResult',row(2,'1|1|1|1'));X4LAN_PLAYER_CONTROL_LIVE_TICK()
 assert(logs[#logs-1]:match(' CONTROLLED$'))
end
assert(logs[#logs]:match(' DONE$'));send('Refused');assert(logs[#logs]:match(' ERROR FAULT$'));assert(not pcall(X4LAN_PLAYER_CONTROL_LIVE_TICK))
print('fake X4 control owner checks passed')
