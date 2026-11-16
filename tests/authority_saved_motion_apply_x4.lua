local ffi=require('ffi');ffi.cdef[[void TestAdvance(void);int TestWrites(void);float TestYaw(void);]]
local resolver=dofile('tools/dev/authority_registry_resolve_string.lua')
local module=dofile('src/authority/lua/saved_motion_apply.lua')
local now=1;local sent,logs={},{}
function GetCurRealTime()return now end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)
 local arg={...};if arg[1]=='isdocked' then return false,false,false end
 if arg[1]=='macro' and tonumber(ref)==41 then return 'ship_ter_m_corvette_01_a_macro','pioneers' end
 if arg[1]=='macro' and tonumber(ref)==43 then return 'cluster_115_sector001_macro' end
 error('unexpected read')
end
function AddUITriggeredEvent(screen,control,args)assert(screen=='X4AuthoritySavedMotionApply' and control=='Inspect');sent[#sent+1]=args;return true end
local writer=assert(module.new_x4({enabled=true,test_profile='45841',expected_save_path='/private/45841/save',resolve=resolver,guard=function()return true end,
 timeout=5,log=function(v)logs[#logs+1]=v;return true end,fault=function(reason)print('fault',reason)end}))
local request=('a'):rep(32)
assert(writer:begin({request=request,epoch=('b'):rep(32),generation=('c'):rep(32),digest=('d'):rep(64),index=1318,sequence=1,
 sector_macro='cluster_115_sector001_macro',actor_key='41',sector_key='43',zone_key='45',target={x=10,y=0,z=0}}))
assert(ffi.C.TestWrites()==0 and sent[1].request_id==request..'-pre')
assert(writer:event(sent[1].request_id..'|ok') and ffi.C.TestWrites()==1 and math.abs(ffi.C.TestYaw()-90)<0.001)
now=2.1;ffi.C.TestAdvance();assert(writer:tick() and sent[2].request_id==request..'-post')
assert(writer:event(sent[2].request_id..'|ok') and writer:state()=='done' and #logs==3)
print('fake X4 setter ABI and delayed readback passed')
