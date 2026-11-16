local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true);ffi.cdef[[void TestMove(void);]]
local nonce,epoch=string.rep('a',32),string.rep('b',32);local requests={};local pre,post=0,0;local badowner=false
function GetCurRealTime()return 1 end
function AddUITriggeredEvent(s,o,a)requests[#requests+1]={s,o,a}end
function ConvertStringToLuaID(s)local v=ffi.new('uint64_t',0);for d in s:gmatch('%d') do v=v*10+tonumber(d) end;return v end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v)end
function GetComponentData(_,a,b,c)
 if a=='owner' then return badowner and 'other' or 'player' end
 assert(a=='isdocked' and b=='isdocking' and c=='isinternallystored');return false,false,false
end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local M=dofile('tools/dev/authority_player_control_once.lua')
local a=M.new_x4{enabled=true,epoch=epoch,nonce=nonce,timeout=10,expected_save_path='/tmp/45841/save',
 pre_guard=function()pre=pre+1;return true end,post_guard=function()post=post+1;return true end}
local function row(seq,flags,owner)return nonce..'|'..epoch..'|'..seq..'|0x20000000000001|0xb|'..flags..'|1|'..(owner or 'player')end
assert(a:tick());assert(requests[#requests][2]=='Create');assert(a:created(nonce..'|'..epoch..'|0x20000000000001|0xb'))
assert(a:tick() and requests[#requests][3].seq==0)
if arg[2]=='wrong_before' then assert(not a:response(row(0,'1|0|0|1')));return end
assert(a:response(row(0,'0|0|0|1')))
assert(a:tick() and requests[#requests][2]=='Teleport');fake.TestMove()
if arg[2]=='owner_changed' then badowner=true;assert(not a:dispatched(nonce..'|'..epoch));return end
assert(a:dispatched(nonce..'|'..epoch))
assert(a:tick() and requests[#requests][3].seq==1)
if arg[2]=='wrong_after' then assert(not a:response(row(1,'0|1|1|1')));return end
assert(a:response(row(1,'1|1|1|1')))
assert(a:tick() and requests[#requests][3].seq==2);local ok,r=a:response(row(2,'1|1|1|1'))
assert(ok and r.status=='controlled' and pre>0 and post>0);assert(not a:response(row(2,'1|1|1|1')))
print('fake X4 player-control readback passed')
