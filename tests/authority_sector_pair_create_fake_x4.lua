local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
local count=0;local handlers={};local sent={};local values={};local epoch=string.rep('a',32);local attempt=string.rep('b',32);local nonce=string.rep('c',32)
function RegisterEvent(name,callback)assert(not handlers[name]);handlers[name]=callback end
function AddUITriggeredEvent(screen,op,args) sent[#sent+1]={screen=screen,op=op,args=args};if op=='Create' then count=1 end;return true end
function GetCurRealTime()return 1 end
function ConvertStringToLuaID(v)return ffi.new('uint64_t',tonumber(v)) end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v) end
function GetComponentData(_,field)assert(field=='macro');return 'ship_arg_s_fighter_01_a_macro' end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_AUTHORITY_SHIP_ENGINE={new=function()return {
 fleet_count=function()return count end,fleet=function(_,cap)assert(cap==count+1);return count==0 and {} or {ffi.new('uint64_t',10)},false end
}end}
local Driver=dofile('tools/dev/authority_sector_pair_create.lua')
local Adapter=dofile('tools/dev/authority_sector_pair_create_x4.lua')
local owner=assert(Adapter.new({enabled=true,exclusive_events=true,expected_save_path='/tmp/45841/save',driver=Driver,role='source',epoch=epoch,attempt=attempt,nonce=nonce,sector='sector_one',timeout=10,
 emit_descriptor=function(v)values[#values+1]=v;return true end,inspect_complete=function()error('unexpected')end,fault=function()error('fault')end}))
assert(owner:start());handlers['X4AuthorityShipCreateReceiver.Initialized'](nil,epoch)
handlers['X4AuthorityShipCreateReceiver.Created'](nil,3)
handlers['X4AuthorityPairCreateInspect.Result'](nil,nonce..'-1|'..epoch..'|0xa|0xb|sector_one')
handlers['X4AuthorityShipCreateReceiver.Created'](nil,3)
handlers['X4AuthorityPairCreateInspect.Result'](nil,nonce..'-2|'..epoch..'|0xa|0xb|sector_one')
assert(owner:state()=='await_ack' and #values==1)
assert(values[1].x==-399.125 and values[1].y==100000 and values[1].z==500.25 and values[1].actor==nil)
assert(owner:confirm_ack({attempt=attempt,epoch=epoch,sequence=1,index=3}));assert(owner:state()=='done')
print('fake FFI passed')
