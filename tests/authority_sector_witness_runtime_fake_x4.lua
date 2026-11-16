local ffi=require('ffi');ffi.cdef[[void test_context(bool);void test_pause(bool);]];local fake=ffi.load(assert(arg[1]),true)
local epoch,rid=string.rep('a',32),string.rep('b',32);local issued={};local dock=false
function GetCurRealTime()return 1 end
function AddUITriggeredEvent(screen,op,args)issued[#issued+1]={screen=screen,args=args} end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v)end
function ConvertStringToLuaID(v)local n=ffi.new('uint64_t',0);for d in v:gmatch('%d') do n=n*10+tonumber(d) end;return n end
function GetComponentData(_,a,b,c)assert(a=='isdocked' and b=='isdocking' and c=='isinternallystored');return dock,false,false end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local M=dofile('tools/dev/authority_sector_witness_runtime.lua')
local opts={enabled=true,epoch=epoch,request_id=rid,index=2,macro='sector_a',timeout=5,expected_save_path='/tmp/45841/save',guard=function()return true end}
local response=rid..'|'..epoch..'|2|ok|0x20000000000001|0x2|sector_a'
local p=M.new_x4(opts);assert(p:start());local ok,row=p:response(response);assert(ok and row.local_witness_match and row.actor==nil)
dock=true;p=M.new_x4(opts);assert(p:start());assert(not p:response(response));dock=false
fake.test_context(false);p=M.new_x4(opts);assert(p:start());assert(not p:response(response));fake.test_context(true)
fake.test_pause(false);p=M.new_x4(opts);assert(not p:start());fake.test_pause(true)
print('fake X4 sector witness checks passed')
