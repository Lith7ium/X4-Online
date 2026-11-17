-- Fake X4 ABI: exercise the actual private owner, not a native game.
local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
ffi.cdef[[void TestMove(void);void TestRogue(void);]]
local existing=arg[3]=='existing'
if existing then fake.TestMove() end
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local events,requests,logs={},{},{}
function RegisterEvent(name,fn) assert(not events[name]);events[name]=fn end
function DebugError(value) logs[#logs+1]=value end
function GetCurRealTime() return 1 end
function AddUITriggeredEvent(screen,operation,args) requests[#requests+1]={screen,operation,args};return true end
function ConvertStringToLuaID(value)
 local id=ffi.new('uint64_t',0);for digit in value:gmatch('%d') do id=id*10+tonumber(digit) end;return id
end
function ConvertIDTo64Bit(value) return ffi.new('uint64_t',value) end
function GetComponentData(_,first,second,third)
 if first=='owner' then return 'player' end
 assert(first=='isdocked' and second=='isdocking' and third=='isinternallystored')
 return false,false,false
end
X4LAN_CONFIG={authority_registered_player_control=true,authority_fixture_timeout=20,authority_fixture_nonce=nonce,
 authority_fixture_epoch=epoch,authority_fixture_slot=existing and 1 or 2,authority_load_save_path='/tmp/45841/save'}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
dofile(assert(arg[2]));dofile('tools/dev/authority_player_control_live_owner.lua')
dofile('tools/dev/authority_registered_player_control_owner.lua')
local function send(name,value) events['X4AuthorityPlayerControlOnce.'..name](nil,value) end
local function row(seq,flags) return nonce..'|'..epoch..'|'..seq..'|0x20000000000001|0xb|'..flags..'|1|player' end
assert(not X4LAN_REGISTERED_PLAYER_CONTROL_TICK())
assert(requests[#requests][2]=='Create' and requests[#requests][3].slot==(existing and 1 or 2))
send('Created',nonce..'|'..epoch..'|0x20000000000001|0xb')
assert(not X4LAN_REGISTERED_PLAYER_CONTROL_TICK())
send('ReadResult',row(0,existing and '1|1|1|1' or '0|0|0|1'))
if not existing then
 assert(not X4LAN_REGISTERED_PLAYER_CONTROL_TICK() and requests[#requests][2]=='Teleport')
 fake.TestMove();send('Dispatched',nonce..'|'..epoch)
end
assert(not X4LAN_REGISTERED_PLAYER_CONTROL_TICK());send('ReadResult',row(1,'1|1|1|1'))
assert(not X4LAN_REGISTERED_PLAYER_CONTROL_TICK());send('ReadResult',row(2,'1|1|1|1'))
assert(X4LAN_REGISTERED_PLAYER_CONTROL_TICK())
local slot=existing and 1 or 2
assert(logs[#logs]:match(' FENCED slot='..slot..' index='..(slot+2)..'$'))
local teleports=0;for _,request in ipairs(requests) do if request[2]=='Teleport' then teleports=teleports+1 end end
assert(teleports==(existing and 0 or 1))
