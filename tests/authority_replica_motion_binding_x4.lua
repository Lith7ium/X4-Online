local ffi=require('ffi');ffi.cdef[[void TestPause(bool);void TestLive(bool);void TestZone(uint64_t);]]
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local M=dofile('src/authority/lua/replica_motion_binding.lua')
local epoch,generation,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32)
local requests,done={},{};local time=1;local docked=false
function GetCurRealTime()return time end
function AddUITriggeredEvent(screen,op,args)assert(screen=='X4AuthorityReplicaMotionBind' and op=='Bind');requests[#requests+1]=args;return true end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s)) end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)assert(ref==41);return docked,false,false end
local function sample(seq)return {epoch=epoch,generation=generation,index=42,sequence=seq,sector_macro='sector_a'}end
local c=assert(M.new_x4({enabled=true,epoch=epoch,generation=generation,index=42,sector_macro='sector_a',nonce=nonce,
 expected_save_path='/private/45841/save',timeout=2,max_age=1,guard=function()return true end,resolve=resolve,
 complete=function(r)done[#done+1]=r;return true end}))
assert(c:begin(sample(1),1));assert(c:event(requests[1].request_id..'|Bound|42|0x29|0x2b'))
assert(c:begin(sample(2),1))
local mode=os.getenv('TEST_BIND_FAILURE') or 'zone'
if mode=='zone' then ffi.C.TestZone(46) elseif mode=='dock' then docked=true elseif mode=='pause' then ffi.C.TestPause(true) elseif mode=='despawn' then ffi.C.TestLive(false) else error('unknown mode') end
assert(not c:event(requests[2].request_id..'|Bound|42|0x29|0x2b') and #done==1)
print('replica binding fake X4 ABI checks passed')
