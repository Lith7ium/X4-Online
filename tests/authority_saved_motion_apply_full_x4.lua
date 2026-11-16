-- Actual motion owner + saved binder + writer; fake C ABI, simulated MD.
local ffi=require('ffi');ffi.cdef[[void TestAdvance(void);int TestWrites(void);]]
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local replica=dofile('src/authority/lua/replica_motion_binding.lua')
local saved=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
local buffer=dofile('src/authority/lua/motion_buffer.lua')
local setter=dofile('src/authority/lua/saved_motion_apply.lua')
local core=dofile('src/authority/lua/motion_client_owner.lua')
local events,requests,input,out={}, {}, {}, {};local now=1
function RegisterEvent(name,cb)assert(not events[name]);events[name]=cb;return true end
function GetCurRealTime()return now end
function AddUITriggeredEvent(screen,op,args)requests[#requests+1]={screen=screen,args=args};return true end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)
 local arg={...};if arg[1]=='isdocked' then return false,false,false end
 if arg[1]=='macro' and tonumber(ref)==41 then return 'ship_ter_m_corvette_01_a_macro','pioneers' end
 if arg[1]=='macro' and tonumber(ref)==43 then return 'cluster_115_sector001_macro' end
 error('unexpected read')
end
local lease,attempt,epoch,generation,nonce=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32),('e'):rep(32)
local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
local owner=assert(core.new_x4({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,nonce=nonce,
 timeout=5,max_age=5,max_tracks=10,guard=function()return true end,net=net,fault=function()end,
 expected_save_path='/private/45841/save',resolve=resolve,binding=replica,buffer=buffer,
 saved_baseline={enabled=true,baseline=10054,guard=function()return true end,binding=saved},
 saved_apply={enabled=true,module=setter,log=function()return true end}}))
assert(owner:start())
local digest=('1'):rep(64)
input[1]=table.concat({'M',lease,attempt,'BIND',('f'):rep(32),epoch,generation,'1318','1','cluster_115_sector001_macro',digest,'10','10','0','0','-','-','-'},'|')
assert(owner:tick());local binding=requests[#requests];assert(binding.screen=='X4AuthoritySavedBaselineMotionBind')
events['X4AuthoritySavedBaselineMotionBind.Result'](nil,binding.args.request_id..'|Bound|1318|0x29|0x2b')
assert(owner:state()=='ready' and #out==2)
local req=('2'):rep(32);input[1]=table.concat({'M',lease,attempt,'APPLY',req,epoch,generation,'1318','1',digest},'|')
assert(owner:tick() and requests[#requests].screen=='X4AuthoritySavedMotionApply' and ffi.C.TestWrites()==0)
events['X4AuthoritySavedMotionApply.Result'](nil,req..'-pre|ok');assert(ffi.C.TestWrites()==1 and #out==2)
now=2.1;ffi.C.TestAdvance();assert(owner:tick() and requests[#requests].args.request_id==req..'-post')
events['X4AuthoritySavedMotionApply.Result'](nil,req..'-post|ok');assert(#out==2)
assert(owner:tick() and #out==3 and out[3]:find('|APPLIED|',1,true))
print('actual saved binder and one-shot owner with fake X4 ABI passed')
