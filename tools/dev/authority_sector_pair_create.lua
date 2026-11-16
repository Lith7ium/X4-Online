-- Default-off single-index test state. No registration, sockets or updates on import.
-- Callers own one event/update loop and supply nonblocking callbacks.
local M={}
local inspect='X4AuthorityPairCreateInspect'
local receiver='X4AuthorityShipCreateReceiver'
local keys={attempt=true,epoch=true,sequence=true,index=true,macro=true,sector=true,owner=true,seed=true,x=true,y=true,z=true}
local function token(s)return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function name(s)return type(s)=='string' and #s>0 and #s<=128 and s:match('^[%w_%-%.]+$')~=nil and s~='nil' and s~='null' end
local function descriptor(v,epoch,attempt,sector)
 if type(v)~='table' then return false end
 local n=0;for k in pairs(v) do if not keys[k] then return false end;n=n+1 end
 if n~=11 or v.epoch~=epoch or v.attempt~=attempt or v.sequence~=1 or v.index~=3 or
  v.macro~='ship_arg_s_fighter_01_a_macro' or v.sector~=sector or v.owner~='argon' or
  v.seed~=7183 or not name(v.sector) then return false end
 for _,k in ipairs({'x','y','z'}) do if not finite(v[k]) or math.abs(v[k])>10000000 then return false end end
 return true
end
local function copy(v)local out={};for k in pairs(keys) do out[k]=v[k] end;return out end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert((o.role=='source' or o.role=='client') and token(o.epoch) and token(o.attempt) and token(o.nonce) and name(o.sector))
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,k in ipairs({'clock','guard','count','issue','snapshot','emit_descriptor','inspect_complete'}) do assert(type(o[k])=='function',k..' required') end
 local phase='new';local failed,busy=false,false;local last,deadline,game0,baseline,req,actor_key,sector_key
 local stage=1
 local function fail(s) failed=true;phase='failed';return false,s end
 local function call(f,...)
  if busy then return fail('reentrant') end
  busy=true;local ok,a,b=pcall(f,...);busy=false
  if not ok or failed then return fail('callback') end
  return true,a,b
 end
 local function check(allow_done)
  if failed or (phase=='done' and not allow_done) then return false end
  local ok,t=call(o.clock);if not ok then return false end
  if not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return fail('deadline') end
  last=t
  local valid,alive,game=call(o.guard)
  if not valid or alive~=true or not finite(game) or game<0 or (game0 and game~=game0) then return fail('guard') end
  game0=game0 or game
  local ok2,t2=call(o.clock);if not ok2 or not finite(t2) or t2<last or (deadline and t2>=deadline) then return fail('deadline') end
  last=t2;return true
 end
 local function counted(expected)
  if not check() then return false end
  local ok,n=call(o.count)
  if not ok or not finite(n) or n%1~=0 or n~=expected then return fail('count') end
  return check()
 end
 local function issue(screen,op,args,nextphase)
  if not check() then return false end
  phase=nextphase
  local ok,v=call(o.issue,screen,op,args)
  if not ok or v~=true then return fail('dispatch') end
  return check()
 end
 local function request_create(v)
  req=copy(v)
  return issue(receiver,'Create',{epoch=req.epoch,index=3,macro=req.macro,sector=req.sector,owner=req.owner,seed=req.seed,x=req.x,y=req.y,z=req.z},'creating')
 end
 local api={}
 function api:start()
  if phase~='new' then return fail('start') end
  local ok,t=call(o.clock);if not ok or not finite(t) or t<0 then return fail('clock') end
  last=t;deadline=t+o.timeout;if not finite(deadline) or not check() then return fail('deadline') end
  local good,n=call(o.count);if not good or not finite(n) or n<0 or n%1~=0 then return fail('baseline') end
  baseline=n
  return issue(receiver,'Initialize',{epoch=o.epoch},'initializing')
 end
 function api:accept_descriptor(v)
  if phase~='await_descriptor' or o.role~='client' or not check() or not descriptor(v,o.epoch,o.attempt,o.sector) then return fail('descriptor') end
  return request_create(v)
 end
 function api:event(event,value)
  if phase=='done' then return fail('late_event') end
  if not check() then return false end
  if event==receiver..'.Refused' or event==inspect..'.Refused' then return fail('refused') end
  if phase=='initializing' and event==receiver..'.Initialized' then
   if value~=o.epoch or not counted(baseline) then return fail('initialize') end
   if o.role=='client' then phase='await_descriptor';return true end
   return request_create({attempt=o.attempt,epoch=o.epoch,sequence=1,index=3,macro='ship_arg_s_fighter_01_a_macro',sector=o.sector,owner='argon',seed=7183,x=-400,y=100000,z=500})
  elseif phase=='creating' and event==receiver..'.Created' then
   if type(value)~='number' or value~=3 or not counted(baseline+1) then return fail('created') end
   local a=copy(req);a.request_id=o.nonce..'-'..stage;return issue(inspect,'Inspect',a,'inspecting')
  elseif phase=='inspecting' and event==inspect..'.Result' then
   if type(value)~='string' or #value>700 then return fail('inspect') end
   local nonce,epoch,actor,sector,macro=value:match('^([0-9a-f%-]+)|([0-9a-f]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([%w_%-%.]+)$')
   if nonce~=o.nonce..'-'..stage or epoch~=o.epoch or macro~=req.sector then return fail('correlation') end
   local ok,p=call(o.snapshot,actor,sector)
   if not ok or type(p)~='table' or not finite(p.x) or not finite(p.y) or not finite(p.z) or
    type(p.actor_key)~='string' or not p.actor_key:match('^[1-9]%d*$') or
    type(p.sector_key)~='string' or not p.sector_key:match('^[1-9]%d*$') or
    math.abs(p.x-req.x)>2 or math.abs(p.y-req.y)>2 or math.abs(p.z-req.z)>2 or not counted(baseline+1) then return fail('snapshot') end
   if stage==1 then
    actor_key,sector_key=p.actor_key,p.sector_key;stage=2
    return request_create(req)
   end
   if actor_key~=p.actor_key or sector_key~=p.sector_key then return fail('changed_binding') end
   if not check() then return false end
   if o.role=='source' then
    local out=copy(req);out.x,out.y,out.z=p.x,p.y,p.z
    if not descriptor(out,o.epoch,o.attempt,o.sector) then return fail('source_position') end
    phase='delivering';local sent,accepted=call(o.emit_descriptor,out)
    if not sent or accepted~=true or not check() then return fail('send') end
    phase='await_ack';return true
   else
    phase='completing';local sent,accepted=call(o.inspect_complete,{attempt=o.attempt,epoch=o.epoch,sequence=1,index=3})
    if not sent or accepted~=true or not check() then return fail('complete') end
   end
   phase='done';return true
  end
  return fail('unexpected_event')
 end
 function api:confirm_ack(v)
  if phase~='await_ack' or o.role~='source' or not check() or type(v)~='table' then return fail('ack') end
  local count=0;for k in pairs(v) do if k~='attempt' and k~='epoch' and k~='sequence' and k~='index' then return fail('ack') end;count=count+1 end
  if count~=4 or v.attempt~=o.attempt or v.epoch~=o.epoch or v.sequence~=1 or v.index~=3 then return fail('ack') end
  phase='done';return true
 end
 function api:tick() return check(true) end
 function api:state()return phase end
 return api
end
return M
