local ffi=require('ffi');ffi.cdef[[void TestPause(bool);void TestLive(bool);void TestZone(uint64_t);]]
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local replica=dofile('src/authority/lua/replica_motion_binding.lua')
local M=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
local epoch,generation,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32)
local requests,done={},{};local time=1;local docked=false;local healthy=true;local checkpoint_ok=true
function GetCurRealTime()return time end
function AddUITriggeredEvent(screen,op,args)
 assert(screen=='X4AuthoritySavedBaselineMotionBind' and op=='Bind' and args.baseline==10054)
 requests[#requests+1]=args;return true
end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)assert(ref==41);return docked,false,false end
local mutate=false
local options={enabled=true,epoch=epoch,generation=generation,index=42,baseline=10054,sector_macro='sector_a',nonce=nonce,
 expected_save_path='/private/45841/save',timeout=2,max_age=1,guard=function()return healthy end,
 saved_baseline_guard=function(e,b)return checkpoint_ok and e==epoch and b==10054 end,resolve=resolve,replica=replica,
 complete=function(r)
  assert(r.evidence=='local_saved_registry' and r.checkpoint_identity_proven==false and r.cross_process_identity_proven==false)
  if mutate then r.checkpoint_identity_proven=true end
  done[#done+1]=r;return true
 end}
local function sample(seq)return {epoch=epoch,generation=generation,index=42,sequence=seq,sector_macro='sector_a'}end
local function response(q)return q.request_id..'|Bound|42|0x29|0x2b'end
local mode=os.getenv('TEST_BIND_FAILURE') or 'ok'
if mode=='bad_index' then options.index=10055;assert(not pcall(M.new_x4,options));return end
if mode=='direct_without_guard' then options.saved_baseline_guard=nil;assert(not pcall(replica.new_saved_baseline_x4,options));return end
local c=assert(M.new_x4(options))
if mode=='pre_guard' then checkpoint_ok=false;assert(not c:begin(sample(1),1) and #requests==0);return end
assert(c:begin(sample(1),1))
if mode=='zone' then
 assert(c:event(response(requests[1])));assert(c:begin(sample(2),1));ffi.C.TestZone(46)
 assert(not c:event(response(requests[2])) and c:state()=='failed' and #done==1);return
end
if mode=='guard' then checkpoint_ok=false
elseif mode=='dock' then docked=true
elseif mode=='pause' then ffi.C.TestPause(true)
elseif mode=='despawn' then ffi.C.TestLive(false)
elseif mode=='mutate' then mutate=true
elseif mode=='stale' then time=3.1
elseif mode=='unavailable' then assert(not c:event(requests[1].request_id..'|Unavailable|') and #done==0);return
elseif mode=='old_event' then assert(not c:event(string.rep('d',32)..'-42-1|Bound|42|0x29|0x2b') and #done==0);return
elseif mode~='ok' then error('unknown mode')end
if mode=='ok' then
 assert(c:event(response(requests[1])) and #done==1)
 for k in pairs(done[1])do assert(k=='epoch' or k=='generation' or k=='index' or k=='sequence' or k=='sector_macro' or k=='evidence' or k=='checkpoint_identity_proven' or k=='cross_process_identity_proven')end
 assert(c:begin(sample(2),1));assert(c:event(response(requests[2])) and #done==2)
else assert(not c:event(response(requests[1])) and c:state()=='failed')end
