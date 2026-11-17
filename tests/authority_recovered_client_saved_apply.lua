-- Recovery overlay with real Lua components, fake X4 ABI and simulated MD.
local ffi=require('ffi');ffi.cdef[[void TestAdvance(void);int TestWrites(void);void TestSetRecoveryCode(bool);]]
local events,requests,input,out,logs={}, {}, {}, {}, {};local now=1;local reject_inspection=false
ffi.C.TestSetRecoveryCode(true)
function RegisterEvent(name,cb)assert(not events[name]);events[name]=cb;return true end
function GetCurRealTime()return now end
function AddUITriggeredEvent(screen,op,args)requests[#requests+1]={screen=screen,args=args};return true end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)
 local args={...};if args[1]=='isdocked' then return false,false,false end
 if reject_inspection then error('synthetic inspection failure') end
 if args[1]=='macro' and tonumber(ref)==41 then return 'ship_arg_m_trans_container_02_b_macro','antigone' end
 if args[1]=='macro' and tonumber(ref)==43 then return 'cluster_06_sector001_macro' end
 error('unexpected read')
end
function DebugError(value)logs[#logs+1]=value end
function X4LAN_RECOVERED_CLIENT_LOAD_READY()return true end
local net={send=function(_,value)out[#out+1]=value;return true end,
 pending=function()return #input>0 end,receive=function()return table.remove(input,1)end}
package.loadlib=function()return function()return {open=function(_,port)assert(port==2345);return net end,monotonic=function()return now end}end end
X4LAN_LOCAL_UDP_MODULE=dofile('src/authority/lua/local_udp_module.lua')
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_REPLICA_MOTION_BINDING=dofile('src/authority/lua/replica_motion_binding.lua')
X4LAN_SAVED_BASELINE_MOTION_BINDING=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
X4LAN_MOTION_BUFFER=dofile('src/authority/lua/motion_buffer.lua')
X4LAN_SAVED_MOTION_APPLY=dofile('src/authority/lua/saved_motion_apply.lua')
X4LAN_CLIENT_MOTION_EVENT_ROUTER=dofile('src/authority/lua/client_motion_event_router.lua')
X4LAN_MOTION_CLIENT_OWNER=dofile('src/authority/lua/motion_client_owner.lua')
local module=dofile('tools/dev/authority_recovered_client_motion.lua')
local lease,attempt,epoch,generation,nonce,router_generation=('a'):rep(32),('b'):rep(32),
 '4ba7be438ebb04ec5bb85fdb95b5a488',('d'):rep(32),('e'):rep(32),('9'):rep(32)
local config={enabled=true,port=2345,lease=lease,attempt=attempt,epoch=epoch,generation=generation,nonce=nonce,
 router_generation=router_generation,baseline=10082,index=1318,timeout=5,expected_save_path='/private/45841/save',
 saved_apply_fixture='recovery_enh_870'}
for _,entry in ipairs({{'index',1317},{'epoch',('c'):rep(32)},{'saved_apply_fixture','other'}}) do
 local old=config[entry[1]];config[entry[1]]=entry[2];assert(not pcall(module.new_x4,config));config[entry[1]]=old
end
local owner=assert(module.new_x4(config));local digest=('1'):rep(64);local mode=arg[1]
local function packet(kind,request,sequence)
 return table.concat({'M',lease,attempt,kind,request,epoch,generation,'1318',sequence or '1',digest},'|')
end
input[1]=table.concat({'M',lease,attempt,'BIND',('f'):rep(32),epoch,generation,'1318','1',
 mode=='sector' and 'other_sector' or 'cluster_06_sector001_macro',digest,'10','10','0','0','-','-','-'},'|')
if mode=='sector' then assert(not owner:tick() and ffi.C.TestWrites()==0);return end
assert(owner:tick());local binding=requests[#requests]
events['X4AuthoritySavedBaselineMotionBind.Result'](nil,binding.args.request_id..'|Bound|1318|0x29|0x2b')
assert(owner:state()=='ready' and out[#out]:find('|BOUND|',1,true))
local pre=('3'):rep(32);local apply=('2'):rep(32)
if mode=='apply_first' then input[1]=packet('APPLY',apply);assert(not owner:tick() and ffi.C.TestWrites()==0);return end
if mode=='wrong_sequence' then input[1]=packet('PREFLIGHT',pre,'2');assert(not owner:tick() and ffi.C.TestWrites()==0);return end
input[1]=packet('PREFLIGHT',pre);assert(owner:tick())
if mode=='preflight_fault' then
 reject_inspection=true
 events['X4AuthoritySavedMotionApply.Result'](nil,nonce..'-'..pre..'-pre|ok')
 assert(owner:state()=='failed' and ffi.C.TestWrites()==0)
 assert(logs[#logs]=='[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR reason=owner_preflight_pre_inspect',tostring(logs[#logs]))
 return
end
events['X4AuthoritySavedMotionApply.Result'](nil,nonce..'-'..pre..'-pre|ok')
assert(owner:tick() and out[#out]:find('|PREFLIGHTED|',1,true) and ffi.C.TestWrites()==0)
if mode=='repeat_preflight' then input[1]=packet('PREFLIGHT',('4'):rep(32));assert(not owner:tick() and ffi.C.TestWrites()==0);return end
input[1]=packet('APPLY',apply);assert(owner:tick())
events['X4AuthoritySavedMotionApply.Result'](nil,nonce..'-'..apply..'-pre|ok');assert(ffi.C.TestWrites()==1)
now=2.1;ffi.C.TestAdvance();assert(owner:tick())
events['X4AuthoritySavedMotionApply.Result'](nil,nonce..'-'..apply..'-post|ok')
assert(owner:tick() and out[#out]:find('|APPLIED|',1,true))
if mode=='repeat_apply' then
 input[1]=packet('APPLY',('5'):rep(32));assert(not owner:tick() and ffi.C.TestWrites()==1)
else
 input[1]=table.concat({'M',lease,attempt,'STOP',('8'):rep(32),epoch,generation},'|')
 assert(owner:tick() and owner:state()=='stopped' and out[#out]:find('|STOPPED|',1,true))
 assert(owner:tick() and ffi.C.TestWrites()==1)
end
print('recovery overlay one-shot with fake X4 ABI passed')
