local ffi=require('ffi');ffi.cdef[[void TestReset(void);void TestUnpause(void);void TestPause(void);void TestAdvance(double);]]
ffi.C.TestReset();ffi.C.TestUnpause()
local core=dofile('src/authority/lua/job_client_owner.lua')
local client=dofile('tools/dev/authority_multi_create_client.lua')
local inspector=dofile('src/authority/lua/x4_multi_create_inspector.lua')
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local lease,attempt,epoch,generation,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32),string.rep('e',32)
local request,digest=string.rep('f',32),string.rep('1',64)
local received,out,sent,handler={},{},{},nil
local now=1
function GetCurRealTime()return now end
function ConvertStringToLuaID(v)return ffi.new('uint64_t',tonumber(v))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(_,...)local r={};for _,k in ipairs({...})do
 if k=='macro' then r[#r+1]='ship_gen_m_tugboat_01_a_macro' elseif k=='owner' then r[#r+1]='pioneers' else r[#r+1]=false end
 end;return unpack(r) end
function RegisterEvent(name,cb)assert(not handler and name=='X4AuthorityMultiCreateReceiver.Result');handler=cb;return true end
function AddUITriggeredEvent(_,op,args)sent[#sent+1]={op=op,args=args};return true end
local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(received,1)end}
local o=assert(core.new_x4({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,nonce=nonce,
 baseline=2,seed=7183,timeout=5,position_tolerance=2,expected_save_path='/private/45841/save',resolve=resolve,
 client=client,inspector_module=inspector,net=net,guard=function()if os.getenv('TEST_GUARD_PAUSE')=='1' then ffi.C.TestPause() end;return true end,witness=function()return 1 end,
 fault=function(r)error(r)end}))
if os.getenv('TEST_GUARD_PAUSE')=='1' then assert(not o:start() and o:state()=='failed');return end
assert(o:start());handler(nil,sent[1].args.request_id..'|Initialized|'..epoch);assert(o:tick());assert(#out==1)
received[1]=table.concat({'P',lease,attempt,'APPLY',request,epoch,generation,'1','3',digest,'ship_gen_m_tugboat_01_a_macro','pioneers','sector_a','-400','100000','500'},'|')
assert(o:tick());assert(sent[2].op=='Create')
handler(nil,sent[2].args.request_id..'|Created|3|0x29');assert(sent[3].op=='Inspect')
ffi.C.TestAdvance(1);handler(nil,sent[3].args.request_id..'|Inspected|3|0x29|0x2b')
assert(#out==1);assert(o:tick());assert(#out==2 and out[2]:match('|APPLIED|'))
assert(not pcall(core.new_x4,{enabled=true}))
