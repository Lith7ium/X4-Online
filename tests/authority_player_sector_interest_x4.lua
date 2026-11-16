local ffi=require('ffi');ffi.cdef[[void TestMode(int);]]
local M=dofile('src/authority/lua/player_sector_interest.lua')
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local id=ffi.new('uint64_t',9007199254740992)+ffi.new('uint64_t',1);local opaque=newproxy()
local now=1;local issued,out=nil,{};local epoch,inc,nonce=('a'):rep(32),('b'):rep(32),('c'):rep(32)
function GetCurRealTime()return now end
function AddUITriggeredEvent(_,_,args)issued=args;return true end
function ConvertStringToLuaID(s)assert(s=='9007199254740993');return opaque end
function ConvertIDTo64Bit(ref)assert(ref==opaque);return id end
function GetComponentData(ref,field)assert(ref==opaque and field=='macro');return 'sector_a' end
local function app()return assert(M.new_x4({enabled=true,epoch=epoch,incarnation=inc,nonce=nonce,timeout=5,resolve=X4LAN_RESOLVE_STRING,
 expected_save_path='/private/45841/save',guard=function(i)return i==inc end,complete=function(v)out[#out+1]=v;return true end}))end
local a=app();assert(a:begin());assert(a:event(issued.request_id..'|'..epoch..'|'..inc..'|ok|0x20000000000001|sector_a'))
assert(#out==1 and out[1].sector_macro=='sector_a')
for _,mode in ipairs({1,2,3,4})do ffi.C.TestMode(mode);local b=app();if b:begin() then assert(not b:event(issued.request_id..'|'..epoch..'|'..inc..'|ok|0x20000000000001|sector_a'))end end
ffi.C.TestMode(0);function ConvertIDTo64Bit(_)return id+ffi.new('uint64_t',1)end
local b=app();assert(b:begin());assert(not b:event(issued.request_id..'|'..epoch..'|'..inc..'|ok|0x20000000000001|sector_a'))
print('player sector interest fake X4 checks passed')
