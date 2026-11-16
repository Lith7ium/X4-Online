local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
local nonce,epoch=string.rep('a',32),string.rep('b',32);local requests={};local mode='positive'
function GetCurRealTime() return 1 end
function AddUITriggeredEvent(screen,op,args) requests[#requests+1]={screen,op,args} end
function ConvertStringToLuaID(s)
 local v=ffi.new('uint64_t',0);for d in s:gmatch('%d') do v=v*10+tonumber(d) end;return v
end
function ConvertIDTo64Bit(v) return ffi.new('uint64_t',v) end
function GetComponentData(_,name)
 assert(name=='assignedpilot');if mode=='bad' then error('private error') end
 if mode=='missing' then return nil end;return ffi.new('uint64_t',99)
end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local M=dofile('tools/dev/authority_positive_seat_search.lua')
local function run(m,zone)
 mode=m;local a=M.new_x4{enabled=true,epoch=epoch,nonce=nonce,timeout=5,expected_save_path='/tmp/45841/save'}
 assert(a:start());local ok,result=a:response(nonce..'|'..epoch..'|0x20000000000001|0xb|'..(zone or '0xc')..'|occupied')
 assert(ok and result.same_actor_proven==false);return result
end
assert(run('positive').status=='candidate_observed')
assert(run('missing').reason=='assigned_pilot_not_observed')
assert(run('bad').reason=='getter_or_context_unavailable')
assert(run('positive','0xb').reason=='getter_or_context_unavailable')
print('fake X4 positive-seat binding checks passed')
