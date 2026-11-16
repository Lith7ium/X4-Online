-- Opt-in single census replica state, no X4 calls or event registration on import.
-- A sole caller drives callbacks and must fence processes/transport externally.
local M={}
local SCREEN='X4AuthorityCensusReplica'
local function token(s)return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function natural(n)return type(n)=='number' and n==n and n>=1 and n<=9007199254740991 and n%1==0 end
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function name(s)return type(s)=='string' and #s>0 and #s<=128 and s:match('^[%w_%-%.]+$')~=nil and s:lower()~='nil' and s:lower()~='null' end
local keys={version=true,type=true,attempt=true,epoch=true,transport_sequence=true,job_sequence=true,index=true,macro=true,faction=true,sector_macro=true,x=true,y=true,z=true}
local function valid(d,o)
 if type(d)~='table' then return false end
 local n=0;for k in pairs(d) do if not keys[k] then return false end;n=n+1 end
 if n~=13 or d.version~=1 or d.type~='job_descriptor' or d.attempt~=o.attempt or d.epoch~=o.epoch or d.transport_sequence~=1 or not natural(d.job_sequence) or d.index~=10055 or not name(d.macro) or not name(d.faction) or not name(d.sector_macro) then return false end
 for _,k in ipairs({'x','y','z'}) do if not finite(d[k]) or math.abs(d[k])>10000000 then return false end end
 return true
end
local function copy(d)local r={};for k in pairs(keys)do r[k]=d[k] end;return r end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.attempt) and token(o.nonce) and finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,k in ipairs({'clock','guard','release_guard','issue','count','snapshot'})do assert(type(o[k])=='function',k..' required')end
 local phase='new';local busy=false;local last,deadline,game0,baseline,desc,windex,actor_key,sector_key
 local step=1;local generation={}
 local function fail(s)phase='failed';generation={};return false,s end
 local function call(fn,...)
  if busy then return fail('reentrant') end
  local p,g=phase,generation;busy=true;local ok,a,b=pcall(fn,...);busy=false
  if not ok or p~=phase or g~=generation then return fail('callback') end
  return true,a,b
 end
 local function check(allow_done)
  if phase=='failed' or phase=='closed' or (phase=='done' and not allow_done) then return false end
  local ok,t=call(o.clock);if not ok or not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return fail('deadline') end;last=t
  local g,alive,game=call(o.guard);if not g or alive~=true or not finite(game) or game<0 or (game0 and game~=game0) then return fail('guard') end;game0=game0 or game
  local t_ok,after=call(o.clock);if not t_ok or not finite(after) or after<t or (deadline and after>=deadline) then return fail('deadline') end;last=after
  return true
 end
 local function counted(target)
  if not check() then return false end
  local ok,n=call(o.count,desc.faction,desc.macro)
  if not ok or not finite(n) or n%1~=0 or n~=target then return fail('count') end
  return check()
 end
 local function issue(op,args,nextphase)
  if not check() then return false end
  phase=nextphase;generation={}
  local ok,sent=call(o.issue,SCREEN,op,args)
  if not ok or sent~=true then return fail('dispatch') end
  return check()
 end
 local function request()
  return {epoch=o.epoch,index=10055,macro=desc.macro,faction=desc.faction,sector_macro=desc.sector_macro,
   seed=7183,x=desc.x,y=desc.y,z=desc.z,witness_index=windex}
 end
 local function create()return issue('Create',request(),'creating') end
 local api={}
 function api:start(d,w)
  if phase~='new' or not valid(d,o) or type(w)~='table' or w.epoch~=o.epoch or w.sector_macro~=d.sector_macro or
   not natural(w.index) or w.index>10054 or w.local_witness_match~=true then return fail('input') end
  desc=copy(d);windex=w.index
  if not check() then return false end;deadline=last+o.timeout
  if not finite(deadline) or not check() then return fail('deadline') end
  local ok,n=call(o.count,desc.faction,desc.macro)
  if not ok or not finite(n) or n<0 or n%1~=0 or not check() then return fail('baseline') end;baseline=n
  return issue('Initialize',{epoch=o.epoch},'initializing')
 end
 function api:event(event,value)
  if phase=='done' then return fail('late_event') end
  if not check() then return false end
  if event==SCREEN..'.Refused' then return fail('refused') end
  if phase=='initializing' and event==SCREEN..'.Initialized' then
   if value~=o.epoch or not counted(baseline) then return fail('initialize') end
   return create()
  elseif phase=='creating' and event==SCREEN..'.Created' then
   if type(value)~='number' or value~=10055 or not counted(baseline+1) then return fail('created') end
   local v=request();v.request_id=o.nonce..'-'..step;return issue('Inspect',v,'inspecting')
  elseif phase=='inspecting' and event==SCREEN..'.Inspection' then
   if type(value)~='string' or #value>768 then return fail('inspection') end
   local rid,epoch,index,actor,sector,macro=value:match('^([0-9a-f%-]+)|([0-9a-f]+)|([0-9]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([%w_%-%.]+)$')
   if rid~=o.nonce..'-'..step or epoch~=o.epoch or index~='10055' or macro~=desc.sector_macro then return fail('correlation') end
   local ok,p=call(o.snapshot,actor,sector)
   if not ok or type(p)~='table' or type(p.actor_key)~='string' or not p.actor_key:match('^[1-9]%d*$') or type(p.sector_key)~='string' or not p.sector_key:match('^[1-9]%d*$') or
    not finite(p.x) or not finite(p.y) or not finite(p.z) or math.abs(p.x-desc.x)>2 or math.abs(p.y-desc.y)>2 or math.abs(p.z-desc.z)>2 or not counted(baseline+1) then return fail('snapshot') end
   if step==1 then actor_key,sector_key=p.actor_key,p.sector_key;step=2;return create() end
   if p.actor_key~=actor_key or p.sector_key~=sector_key or not check() then return fail('binding_changed') end
   phase='intent_pending';generation={};return true
  end
  return fail('unexpected_event')
 end
 function api:tick()
  if not check(true) then return false end
  if phase=='intent_pending' then phase='intent_ready';generation={} end
  return true,phase
 end
 function api:take_intent()
  if phase~='intent_ready' or not check() then return fail('intent') end
  local ok,allowed=call(o.release_guard)
  if not ok or allowed~=true or not check() then return fail('release_guard') end
  phase='done';generation={}
  return true,{attempt=o.attempt,epoch=o.epoch,transport_sequence=1,job_sequence=desc.job_sequence,index=10055}
 end
 function api:state()return phase end
 function api:abort()return fail('external_fence')end
 return api
end
return M
