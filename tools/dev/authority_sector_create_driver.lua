-- Experimental default-off state machine; import registers no events or updates.
-- An exclusive owner must dispatch all receiver and inspector events here.
local M={}
local inspect='X4AuthoritySectorCreateInspect'
local receiver='X4AuthorityShipCreateReceiver'
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.nonce) and type(o.macros)=='table' and #o.macros==2 and o.macros[1]~=o.macros[2])
 for _,s in ipairs(o.macros) do assert(type(s)=='string' and #s<=128 and s:match('^[%w_%-%.]+$')) end
 for _,s in ipairs({'issue','clock','guard','count','snapshot','report'}) do assert(type(o[s])=='function',s..' required') end
 local phase='new';local failed=false;local busy=false;local last,deadline,game0,baseline,step=nil,nil,nil,nil,1
 local saved={};local remote=false
 local sequence={{3,3,'create'},{3,3,'replay'},{4,4,'create'},{4,4,'replay'},{3,4,'final'},{4,4,'final'}}
 local function fail(reason) failed=true;phase='failed';return false,reason end
 local function call(fn,...)
  if busy then return fail('reentrant') end
  busy=true;local ok,a,b=pcall(fn,...);busy=false
  if not ok or failed then return fail('callback_failed') end
  return true,a,b
 end
 local function check()
  if failed or phase=='done' then return false end
  local ok,t=call(o.clock);if not ok then return false end
  if not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return fail('timeout') end
  last=t
  local good,valid,game=call(o.guard);if not good then return false end
  if valid~=true or not finite(game) or game<0 or (game0 and game~=game0) then return fail('context') end
  local checked,after=call(o.clock);if not checked then return false end
  if not finite(after) or after<t or (deadline and after>=deadline) then return fail('timeout') end
  last=after;game0=game0 or game;return true
 end
 local function issue(screen,op,args,nextphase)
  if not check() then return false end
  phase=nextphase;deadline=last+5
  local ok,sent=call(o.issue,screen,op,args)
  if not ok or sent~=true then return fail('dispatch') end
  -- The call may have sent a mutation before becoming slow or losing pause.
  -- In that case failure is indeterminate and the owner must discard the case.
  return check()
 end
 local function read_count(expected)
  if not check() then return false end
  local ok,n=call(o.count)
  if not ok or not finite(n) or n%1~=0 or n~=expected then return fail('candidate_count') end
  return check()
 end
 local function inspect_request()
  local row=sequence[step];local id=row[1]
  return issue(inspect,'Inspect',{epoch=o.epoch,index=id,last=row[2],request_id=o.nonce..'-'..step},'inspect')
 end
 local function create_request()
  local row=sequence[step];local slot=row[1]-2
  return issue(receiver,'Create',{epoch=o.epoch,index=row[1],macro='ship_arg_s_fighter_01_a_macro',sector=o.macros[slot],owner='argon',seed=7183,x=-400,y=100000,z=500},'created')
 end
 local api={}
 function api:start()
  if phase~='new' then return fail('start') end
  local clock_ok,t=call(o.clock)
  if not clock_ok or not finite(t) or t<0 then return fail('clock') end
  last=t;deadline=t+5
  if not finite(deadline) or not check() then return fail('start') end
  local ok,n=call(o.count)
  if not ok or not finite(n) or n<0 or n%1~=0 then return fail('baseline_count') end
  baseline=n
  return issue(inspect,'Preflight',{epoch=o.epoch,request_id=o.nonce..'-0'},'preflight')
 end
 function api:event(name,value)
  if phase=='done' then return fail('late_event') end
  if not check() then return false end
  if name==inspect..'.Refused' or name==receiver..'.Refused' then return fail('refused') end
  if phase=='preflight' and name==inspect..'.Preflight' then
   local expected=o.nonce..'-0|'..o.epoch..'|'..o.macros[1]..'|'..o.macros[2]
   if value~=expected or not read_count(baseline) then return fail('preflight') end
   return issue(receiver,'Initialize',{epoch=o.epoch},'initialized')
  elseif phase=='initialized' and name==receiver..'.Initialized' then
   if value~=o.epoch or not read_count(baseline) then return fail('initialize') end
   return create_request()
  elseif phase=='created' and name==receiver..'.Created' then
   local row=sequence[step];if tonumber(value)~=row[1] then return fail('created_index') end
   if not read_count(baseline+(row[1]-2)) then return false end
   return inspect_request()
  elseif phase=='inspect' and name==inspect..'.Result' then
   local row=sequence[step];local id=row[1];local slot=id-2
   if type(value)~='string' or #value>700 then return fail('result_type') end
   local rid,ep,index,actor,sector,macro,location=value:match('^([0-9a-f%-]+)|([0-9a-f]+)|([34])|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([%w_%-%.]+)|([a-z]+)$')
   if rid~=o.nonce..'-'..step or ep~=o.epoch or tonumber(index)~=id or macro~=o.macros[slot] or (location~='local' and location~='remote') then return fail('correlation') end
   local ok,s=call(o.snapshot,actor,sector)
   if not ok or type(s)~='table' or type(s.actor_key)~='string' or not s.actor_key:match('^[1-9]%d*$') or type(s.sector_key)~='string' or not s.sector_key:match('^[1-9]%d*$') or
    not finite(s.x) or not finite(s.y) or not finite(s.z) or math.abs(s.x+400)>2 or math.abs(s.y-100000)>2 or math.abs(s.z-500)>2 then return fail('readback') end
   if saved[id] and (saved[id].actor~=s.actor_key or saved[id].sector~=s.sector_key or saved[id].location~=location) then return fail('changed_binding') end
   local other=saved[id==3 and 4 or 3]
   if other and (other.actor==s.actor_key or other.sector==s.sector_key) then return fail('duplicate_binding') end
   saved[id]={actor=s.actor_key,sector=s.sector_key,location=location};remote=remote or location=='remote'
   if not read_count(baseline+(row[2]-2)) then return false end
   local reported,accepted=call(o.report,{index=id,stage=row[3],sector_macro=macro,location=location,x=s.x,y=s.y,z=s.z,count=baseline+(row[2]-2),game=game0})
   if not reported or accepted~=true then return fail('report') end
   if not check() then return false end
   step=step+1
   if step>#sequence then
    if not remote then return fail('no_remote_sector') end
    phase='done';deadline=nil;return true,'done'
   end
   if sequence[step][3]=='final' then return inspect_request() end
   return create_request()
  end
  return fail('unexpected_event')
 end
 function api:tick() return check() end
 function api:state() return phase end
 return api
end
return M
