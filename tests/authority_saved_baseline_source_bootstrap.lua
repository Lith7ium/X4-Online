local ffi=require('ffi');ffi.cdef[[void TestReset(void);void TestUnpause(void);void TestPause(void);]]
ffi.C.TestReset();ffi.C.TestUnpause()
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local M=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local requests,completed={},{};local now=1;local baseline=true;local healthy=true;local docked=false;local owner
function GetCurRealTime()return now end
function AddUITriggeredEvent(screen,op,args)assert(screen=='X4AuthorityJobDescriptorProbe' and op=='Read');requests[#requests+1]=args;return true end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)
 if ref==41 then return docked,false,false end
 assert(ref==43 and (...)=='macro');return 'sector_a'
end
local mode=os.getenv('BOOTSTRAP_CASE') or 'ok'
owner=assert(M.new_x4({enabled=true,epoch=epoch,nonce=nonce,baseline=10054,timeout=2,expected_save_path='/private/45841/save',resolve=resolve,
 guard=function()return healthy end,baseline_guard=function(e,b)return baseline and e==epoch and b==10054 end,
 complete=function(index,actor,sector)
  assert(index==1318 and actor==41 and sector=='sector_a')
  completed[#completed+1]=index
  if mode=='reentrant' then owner:close() end
  if mode=='post_dock' then docked=true end
  if mode=='post_guard' then baseline=false end
  return true
 end}))
if mode=='invalid_index' then assert(not owner:begin(10055) and #requests==0);return end
assert(owner:begin(1318));local id=requests[1].request_id;assert(#id==32)
local reply=id..'|'..epoch..'|1318|ok|0x29|ship_a|argon|0x2b|sector_a'
if mode=='foreign' then reply=string.rep('f',32)..reply:sub(33)
elseif mode=='wrong_index' then reply=reply:gsub('|1318|','|1319|')
elseif mode=='wrong_actor' then reply=reply:gsub('|0x29|','|0x2a|')
elseif mode=='wrong_sector' then reply=reply:gsub('|0x2b|','|0x2c|')
elseif mode=='wrong_macro' then reply=reply:gsub('sector_a$','sector_b')
elseif mode=='dock' then docked=true
elseif mode=='guard' then baseline=false
elseif mode=='pause' then ffi.C.TestPause()
elseif mode=='timeout' then now=4
elseif mode=='unavailable' then reply=id..'|'..epoch..'|1318|unavailable'
elseif mode=='foreign_unavailable' then reply=string.rep('f',32)..'|'..epoch..'|1318|unavailable'
elseif mode~='ok' and mode~='reentrant' and mode~='post_dock' and mode~='post_guard' then error('unknown test mode')end
if mode=='ok' then
 assert(owner:event(reply) and owner:state()=='idle' and #completed==1)
 assert(owner:begin(1318));assert(requests[2].request_id~=id)
 assert(not owner:event(reply) and owner:state()=='failed' and #completed==1)
else
 assert(not owner:event(reply) and owner:state()=='failed')
 if mode=='unavailable' then assert(owner:diagnostic()=='md_unavailable')end
 if mode=='foreign_unavailable' then assert(owner:diagnostic()=='correlation')end
 if mode=='wrong_actor' or mode=='wrong_sector' or mode=='wrong_macro' or mode=='dock' then assert(owner:diagnostic()=='inspect_before')end
 if mode=='reentrant' or mode=='post_dock' or mode=='post_guard' then assert(#completed==1)else assert(#completed==0)end
end
