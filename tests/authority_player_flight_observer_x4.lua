local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
ffi.cdef[[void TestResume(void);void TestPause(void);void TestGame(double);void TestRogue(void);void TestInvalid(void);void TestPose(float);void TestZoneLost(void);void TestOccupiedLost(void);void TestContainerLost(void);]]
local epoch,nonce=string.rep('a',32),string.rep('b',32);local t=1;local issued={};local badowner=false;local external_ok=true
function GetCurRealTime()return t end
function AddUITriggeredEvent(s,op,a)issued[#issued+1]={s,op,a}end
function ConvertStringToLuaID(s)local v=ffi.new('uint64_t',0);for d in s:gmatch('%d')do v=v*10+tonumber(d)end;return v end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v)end
function GetComponentData(_,n)assert(n=='owner');return badowner and 'other' or 'player'end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local M=dofile('tools/dev/authority_player_flight_observer.lua')
local app=M.new_x4{enabled=true,epoch=epoch,nonce=nonce,timeout=20,expected_save_path='/tmp/45841/save',owner_id='player',
 target=X4LAN_RESOLVE_STRING.parse_hex('0x20000000000001'),sector=ffi.new('uint64_t',11),parent_zone=ffi.new('uint64_t',12),
 confirmed=function()return true end,external_guard=function()return external_ok end}
local function row(i,actor,zone)return nonce..'|'..epoch..'|'..i..'|'..(actor or '0x20000000000001')..'|0xb|'..(zone or '0xc')..'|player'end
assert(app:arm());assert(app:begin_resume());fake.TestResume();assert(app:tick() and app:state()=='await_running')
t=2;fake.TestGame(4);assert(app:tick() and app:state()=='ready')
if arg[2]=='rogue' then fake.TestRogue();assert(not app:tick());return end
if arg[2]=='owner' then badowner=true;assert(not app:tick());return end
if arg[2]=='zone_lost' then fake.TestZoneLost();assert(not app:tick());return end
if arg[2]=='occupied_lost' then fake.TestOccupiedLost();assert(not app:tick());return end
if arg[2]=='container_lost' then fake.TestContainerLost();assert(not app:tick());return end
if arg[2]=='external_lost' then external_ok=false;assert(not app:tick());return end
assert(app:request('neutral'))
if arg[2]=='actor' then assert(not app:response(row(1,'0xa')));return end
if arg[2]=='zone' then assert(not app:response(row(1,nil,'0xb')));return end
if arg[2]=='nan' then fake.TestInvalid();assert(not app:response(row(1)));return end
local ok,r=app:response(row(1));assert(ok and r.sequence==1 and r.x==0)
for i,label in ipairs({'before','after'}) do t=i+2;fake.TestGame(i+4);fake.TestPose(i);assert(app:request(label));ok,r=app:response(row(i+1));assert(ok and r.x==i and not r.movement_cause_proven)end
assert(app:state()=='done');assert(app:close());assert(not app:response(row(3)))
print('fake X4 flight observer checks passed')
