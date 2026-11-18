-- A fake X4 ABI and simulated MD replies; no native game is started.
local ffi=require('ffi')
ffi.cdef[[void TestSetRecoveryCode(bool); void TestAdvance(void); int TestWrites(void);]]
local resolver=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_REPLICA_MOTION_BINDING=dofile('src/authority/lua/replica_motion_binding.lua')
local module=dofile('src/authority/lua/saved_motion_apply.lua')
local epoch='4ba7be438ebb04ec5bb85fdb95b5a488'
local fixture='recovery_enh_870'
local now,mode,sent=1,nil,{}
function GetCurRealTime()return now end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)
 local fields={...}
 if fields[1]=='isdocked' then return false,false,false end
 if fields[1]=='macro' and tonumber(ref)==41 then
  return mode=='macro' and 'wrong_macro' or 'ship_arg_m_trans_container_02_b_macro',mode=='owner' and 'argon' or 'antigone'
 end
 if fields[1]=='macro' and tonumber(ref)==43 then
  return mode=='sector_live' and 'cluster_115_sector001_macro' or 'cluster_06_sector001_macro'
 end
 error('unexpected read')
end
function AddUITriggeredEvent(screen,control,args)
 assert(screen=='X4AuthoritySavedMotionApply' and control=='Inspect')
 sent[#sent+1]=args
 return true
end
local function create(options)
 options=options or {}
 options.enabled=true;options.test_profile='45841';options.expected_save_path='/private/45841/save'
 options.resolve=resolver;options.guard=function()return true end;options.timeout=5
 options.log=function()return true end;options.fault=function()end
 return module.new_x4(options)
end
local function input()
 return {request=('a'):rep(32),epoch=epoch,generation=('c'):rep(32),digest=('d'):rep(64),
  index=1318,sequence=1,sector_macro='cluster_06_sector001_macro',actor_key='41',sector_key='43',zone_key='45',
  target={x=10,y=0,z=0}}
end
assert(not pcall(create,{fixture='arbitrary'}))
for _,case in ipairs({'epoch','index','sector_input','macro','owner','sector_live','code','md_refused'}) do
 mode=case;sent={};ffi.C.TestSetRecoveryCode(case~='code')
 local writer=assert(create({fixture=fixture}));local sample=input()
 if case=='epoch' then sample.epoch=('e'):rep(32) end
 if case=='index' then sample.index=687 end
 if case=='sector_input' then sample.sector_macro='cluster_115_sector001_macro' end
 local began=writer:begin(sample)
 if case=='epoch' or case=='index' or case=='sector_input' then
  assert(not began and #sent==0)
 else
  assert(began and #sent==1 and sent[1].fixture==fixture and sent[1].epoch==epoch)
  assert(not writer:event(sent[1].request_id..(case=='md_refused' and '|refused' or '|ok')))
 end
 assert(writer:state()=='failed' and ffi.C.TestWrites()==0)
end
-- Mutating caller options after construction cannot change the chosen fixture.
mode=nil;sent={};ffi.C.TestSetRecoveryCode(true)
local options={fixture=fixture};local writer=assert(create(options));options.fixture=nil
assert(writer:begin(input()) and sent[1].fixture==fixture)
assert(writer:event(sent[1].request_id..'|ok') and ffi.C.TestWrites()==1)
now=2.1;ffi.C.TestAdvance();assert(writer:tick() and sent[2].fixture==fixture)
assert(writer:event(sent[2].request_id..'|ok') and writer:state()=='done')
print('recovery fixture with simulated MD and fake X4 ABI passed')
