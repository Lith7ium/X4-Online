local ffi=require('ffi');ffi.cdef[[void TestPause(bool);void TestLive(bool);void TestZone(uint64_t);void TestSetSavePath(const char*);]]
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local M=dofile('src/authority/lua/replica_motion_binding.lua')
local epoch,generation,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32)
local requests,done={},{};local time=1;local docked=false
local path_case=os.getenv('TEST_SAVE_PATH_CASE')
local expected_path='/private/45841/save'
if path_case=='drive_forward' then
 ffi.C.TestSetSavePath('C:/Users/Test/Documents/Egosoft/X4/45841/save')
 expected_path='C:\\Users\\Test\\Documents\\Egosoft\\X4\\45841\\save'
elseif path_case=='drive_backslash' then
 ffi.C.TestSetSavePath('C:\\Users\\Test\\Documents\\Egosoft\\X4\\45841\\save')
 expected_path='C:/Users/Test/Documents/Egosoft/X4/45841/save'
elseif path_case=='unc' then
 ffi.C.TestSetSavePath('\\\\Server\\Share\\Users\\Test\\45841\\save')
 expected_path='//Server/Share/Users/Test/45841/save'
elseif path_case=='wrong_profile' then
 ffi.C.TestSetSavePath('C:/Users/Test/45842/save')
 expected_path='C:/Users/Test/45841/save'
elseif path_case=='case_mismatch' then
 ffi.C.TestSetSavePath('C:/Users/Test/Documents/Egosoft/X4/45841/save')
 expected_path='c:/Users/Test/Documents/Egosoft/X4/45841/save'
elseif path_case=='expected_wrong_profile' then
 expected_path='C:/Users/Test/45842/save'
end
function GetCurRealTime()return time end
function AddUITriggeredEvent(screen,op,args)assert(screen=='X4AuthorityReplicaMotionBind' and op=='Bind');requests[#requests+1]=args;return true end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s)) end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)assert(ref==41);return docked,false,false end
local function sample(seq)return {epoch=epoch,generation=generation,index=42,sequence=seq,sector_macro='sector_a'}end
if path_case=='expected_wrong_profile' then
 assert(not pcall(M.new_x4,{enabled=true,epoch=epoch,generation=generation,index=42,sector_macro='sector_a',nonce=nonce,
  expected_save_path=expected_path,timeout=2,max_age=1,guard=function()return true end,resolve=resolve,complete=function()return true end}))
 print('replica binding invalid expected profile rejected')
 return
end
local c=assert(M.new_x4({enabled=true,epoch=epoch,generation=generation,index=42,sector_macro='sector_a',nonce=nonce,
 expected_save_path=expected_path,timeout=2,max_age=1,guard=function()return true end,resolve=resolve,
 complete=function(r)done[#done+1]=r;return true end}))
if path_case then
 if path_case=='wrong_profile' or path_case=='case_mismatch' then
  assert(not c:begin(sample(1),1) and #requests==0)
 else
  assert(c:begin(sample(1),1));assert(c:event(requests[1].request_id..'|Bound|42|0x29|0x2b'))
  assert(#done==1)
 end
 print('replica binding Windows path fake X4 checks passed')
 return
end
assert(c:begin(sample(1),1));assert(c:event(requests[1].request_id..'|Bound|42|0x29|0x2b'))
assert(c:begin(sample(2),1))
local mode=os.getenv('TEST_BIND_FAILURE') or 'zone'
if mode=='zone' then ffi.C.TestZone(46) elseif mode=='dock' then docked=true elseif mode=='pause' then ffi.C.TestPause(true) elseif mode=='despawn' then ffi.C.TestLive(false) else error('unknown mode') end
assert(not c:event(requests[2].request_id..'|Bound|42|0x29|0x2b') and #done==1)
print('replica binding fake X4 ABI checks passed')
