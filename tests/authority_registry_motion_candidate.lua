-- Actual Lua selector and fake X4 ABI/MD, no game or networking.
local ffi=require('ffi');ffi.cdef[[void TestPause(bool);void TestLive(bool);]]
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local M=dofile('tools/dev/authority_registry_motion_candidate.lua')
local mode=arg[1];local epoch=('a'):rep(32);local nonce=('b'):rep(32)
local requests={};local now=1;local dock=false;local calls=0;local healthy=true;local armed=false;local owner
function GetCurRealTime()return now end
function AddUITriggeredEvent(screen,op,args)assert(screen=='X4AuthorityRegistryMotionCandidate' and op=='Read');requests[#requests+1]=args;return true end
function ConvertStringToLuaID(v)return ffi.new('uint64_t',tonumber(v))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(v,...)
 if v==41 then
  calls=calls+1
  if mode=='reentrant' then owner:event('unexpected') end
  if mode=='nil_getter' then return nil,false,false end
  if mode=='throw_getter' then error('unavailable')end
  if mode=='changing_dock' and calls>1 then return true,false,false end
  return dock,false,false
 end
 assert(v==43 and (...)=='macro');return mode=='wrong_macro' and 'other' or 'sector_a'
end
local candidates={1,2};owner=assert(M.new_x4({enabled=true,epoch=epoch,nonce=nonce,baseline=10082,candidates=candidates,
 timeout=2,expected_save_path='/private/45841/save',resolve=resolve,guard=function()
  if mode=='guard_overrun' and armed then now=4 end
  return healthy
 end,
 baseline_guard=function(e,n)return e==epoch and n==10082 end}))
candidates[2]=8 -- options are captured once
assert(owner:start() and requests[1].index==1);armed=true
local function response(status,suffix)
 local r=requests[#requests]
 return r.request_id..'|'..epoch..'|'..r.index..'|'..status..(suffix or '')
end
local ok='|0x29|0x2b|sector_a'
if mode=='skip' then
 assert(owner:event(response('ineligible')) and requests[2].index==2)
 assert(owner:event(response('ok',ok)));assert(owner:result().index==2 and owner:result().status=='candidate')
elseif mode=='none' then
 assert(owner:event(response('ineligible')) and owner:event(response('ineligible')))
 assert(owner:result().reason=='no_candidate')
elseif mode=='docked' then
 dock=true;assert(owner:event(response('ok',ok)) and requests[2].index==2)
 assert(owner:event(response('ineligible')) and owner:result().status=='inconclusive')
elseif mode=='nil_getter' or mode=='throw_getter' or mode=='changing_dock' or mode=='wrong_macro' then
 assert(owner:event(response('ok',ok)) and owner:result().reason=='getter_or_context_unavailable')
elseif mode=='refused' then
 assert(owner:event(response('refused')) and owner:result().reason=='registry_refused')
elseif mode=='stale' then
 local old=response('ineligible');assert(owner:event(old));assert(not owner:event(old) and owner:state()=='failed')
elseif mode=='guard' then
 healthy=false;assert(not owner:event(response('ok',ok)) and owner:state()=='failed')
elseif mode=='guard_overrun' then
 assert(not owner:event(response('ok',ok)) and owner:state()=='failed')
elseif mode=='reentrant' then
 assert(not owner:event(response('ok',ok)) and owner:state()=='failed')
elseif mode=='wrong_sector' then
 assert(owner:event(response('ok','|0x29|0x2d|sector_a')) and owner:result().reason=='getter_or_context_unavailable')
elseif mode=='malformed' then
 assert(not owner:event(response('ok','|0x29|0x2b|')) and owner:state()=='failed')
elseif mode=='pause' then
 ffi.C.TestPause(true);assert(not owner:event(response('ok',ok)) and owner:state()=='failed')
elseif mode=='timeout' then
 now=3;assert(not owner:tick() and owner:state()=='failed')
elseif mode=='ok' then
 assert(owner:event(response('ok',ok)) and owner:result().index==1 and owner:result().runtime_reservation==false)
else error('unknown case')end
