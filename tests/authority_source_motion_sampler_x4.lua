-- Actual source sampler and existing X4 descriptor reader with fake X4 ABI;
-- the correlated MD response is simulated. No native game is started.
local ffi=require('ffi');ffi.cdef[[void TestReset(void);void TestUnpause(void);void TestAdvance(double);]]
ffi.C.TestReset();ffi.C.TestUnpause()
local sampler=dofile('src/authority/lua/source_motion_sampler.lua')
local descriptor=dofile('tools/dev/authority_job_descriptor_probe.lua')
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local epoch,generation,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32)
local sent,out,errors={}, {}, {};local now=0
function GetCurRealTime()return now end
local conversion='good';local dock_reads=0
function ConvertIDTo64Bit(v)if conversion=='bad_roundtrip' then return 42 end;return v end
function ConvertStringToLuaID(v)if conversion=='wrong_id' then return 42 elseif conversion=='rounded_id' then return 9007199254740992 elseif conversion=='high_exact' then return X4LAN_RESOLVE_STRING.parse_hex('0x20000000000001') end;return tonumber(v) end
local docked=false
function GetComponentData(_,a,b,c)dock_reads=dock_reads+1;assert(a=='isdocked' and b=='isdocking' and c=='isinternallystored');return docked,false,false end
function AddUITriggeredEvent(screen,op,args)assert(screen=='X4AuthorityJobDescriptorProbe' and op=='Read');sent[#sent+1]=args;return true end
local x=assert(sampler.new_x4({enabled=true,epoch=epoch,generation=generation,nonce=nonce,max_tracks=10,scan_budget=2,
 interval=.1,timeout=5,min_dt=.02,max_dt=1,descriptor=descriptor,resolve=X4LAN_RESOLVE_STRING,
 expected_save_path='/private/45841/save',guard=function()return true end,binding_guard=function(row,a)return row.index==1 and a==41 end,
 fault=function(v)errors[#errors+1]=v end}))
assert(x:register({epoch=epoch,index=1,sequence=1,classification='new_registry_entry'},41))
assert(x:tick());local req=sent[1].request_id;assert(req==x:expected_request())
local ok,result=x:event(req..'|'..epoch..'|1|ok|0x29|ship_a|argon|0x2b|sector_a');assert(ok);out[#out+1]=result
assert(out[1].x==-400 and out[1].y==100000 and out[1].velocity==nil and out[1].source_time==100 and out[1].local_sector_key==nil)
now=.2;ffi.C.TestAdvance(.2);assert(x:tick());req=sent[2].request_id;assert(req~=sent[1].request_id)
ok,result=x:event(req..'|'..epoch..'|1|ok|0x29|ship_a|argon|0x2b|sector_a');assert(ok);out[#out+1]=result
assert(out[2].sequence==2 and out[2].velocity and out[2].velocity.x==0 and #errors==0)

-- A newly docked actor fences the sampler before another sample is issued.
docked=true;now=.4;assert(not x:tick() and x:state()=='failed');assert(#out==2)

-- Never read docking state for an ID altered or rounded by conversion.
docked=false
for _,mode in ipairs({'wrong_id','rounded_id','bad_roundtrip'})do
 conversion=mode;local before=dock_reads
 local y=assert(sampler.new_x4({enabled=true,epoch=epoch,generation=generation,nonce=nonce,max_tracks=10,scan_budget=2,
  interval=.1,timeout=5,min_dt=.02,max_dt=1,descriptor=descriptor,resolve=X4LAN_RESOLVE_STRING,
  expected_save_path='/private/45841/save',guard=function()return true end,binding_guard=function()return true end,
  fault=function()end}))
 assert(not y:register({epoch=epoch,index=1,sequence=1,classification='new_registry_entry'},41))
 assert(y:state()=='failed' and dock_reads==before)
end

-- A uint64 actor above 2^53 is accepted only if the local Lua-ID round-trips
-- exactly; a rounded Lua number must be rejected before any property read.
local high=assert(X4LAN_RESOLVE_STRING.parse_hex('0x20000000000001'))
local function new_high()return assert(sampler.new_x4({enabled=true,epoch=epoch,generation=generation,nonce=nonce,max_tracks=10,scan_budget=2,
 interval=.1,timeout=5,min_dt=.02,max_dt=1,descriptor=descriptor,resolve=X4LAN_RESOLVE_STRING,
 expected_save_path='/private/45841/save',guard=function()return true end,binding_guard=function()return true end,fault=function()end}))end
conversion='rounded_id';local before=dock_reads;local bad=new_high()
assert(not bad:register({epoch=epoch,index=1,sequence=1,classification='new_registry_entry'},high) and dock_reads==before)
conversion='high_exact';local good=new_high()
assert(good:register({epoch=epoch,index=1,sequence=1,classification='new_registry_entry'},high) and dock_reads>before)
