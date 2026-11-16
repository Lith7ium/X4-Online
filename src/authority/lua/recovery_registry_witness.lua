-- Private, paused diagnostic only. A successful check establishes that the two
-- saved tables still agree, not that either table retained historical identity.
local M={}
local function hex(v) return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
function M.new(c)
 assert(type(c)=='table' and c.enabled==true and hex(c.epoch) and hex(c.nonce) and c.epoch~=c.nonce)
 assert(c.phase=='create' or c.phase=='verify')
 assert(type(c.count)=='number' and c.count%1==0 and c.count>=1 and c.count<=200000)
 for _,k in ipairs({'clock','paused','issue','register','complete'}) do assert(type(c[k])=='function',k) end
 assert(c.fault==nil or type(c.fault)=='function')
 local state='new';local request,expected,deadline;local serial=0;local index=1;local last;local issuing=false;local current=0
 local function fail(reason)
  local first=state~='failed';state='failed'
  if first and c.fault then pcall(c.fault,c.phase,current,reason) end
  return false
 end
 local function guard()
  local ok,t=pcall(c.clock)
  if not ok then return 'clock' end
  if type(t)~='number' or t~=t or t<0 or t==math.huge or (last and t<last) then return 'clock' end
  if deadline and t>=deadline then return 'deadline' end
  local pause_ok,paused=pcall(c.paused)
  if not pause_ok then return 'pause_check' end
  if paused~=true then return 'not_paused' end
  last=t;return nil
 end
 local function dispatch(control,kind,n,params)
  local reason=guard();if reason then return fail(reason) end
  current=n
  serial=serial+1;request=c.nonce..':'..string.format('%.0f',serial)
  expected=kind..'|'..string.format('%.0f',n)..'|ok';deadline=last+30;state='pending'
  params.request_id=request;params.epoch=c.epoch
  issuing=true;local invoked,ok=pcall(c.issue,'X4AuthorityRegistryWitness',control,params);issuing=false
  if not invoked or ok~=true or state~='pending' then return fail('dispatch') end
  return true
 end
 local api={}
 function api:start()
  if state~='new' then return fail('start_state') end
  local reason=guard();if reason then return fail(reason) end
  if c.phase=='create' then return dispatch('Initialize','init',0,{count=c.count}) end
  return dispatch('BeginVerify','begin',0,{count=c.count})
 end
 function api:event(row)
  if issuing then return fail('reentrant_event') end
  if state~='pending' then return fail('event_state') end
  local reason=guard();if reason then return fail(reason) end
  if type(row)~='string' then return fail('event_type') end
  if row~=request..'|'..c.epoch..'|'..expected then
   if row==request..'|'..c.epoch..'|'..expected:gsub('|ok$','|refused') then return fail('refused') end
   return fail('event_mismatch')
  end
  deadline=nil
  if expected:match('^finish|') then
   state='done'
   local invoked,ok=pcall(c.complete,c.epoch,c.count,c.phase)
   if not invoked or ok~=true then return fail('complete') end
   reason=guard();if reason then return fail(reason) end
  else state='next' end
  return true
 end
 function api:tick()
  if state=='failed' then return false end
  local reason=guard();if reason then return fail(reason) end
  if state=='next' then
   if index<=c.count then
    local i=index;index=index+1
    return dispatch('Step',c.phase,i,{index=i,phase=c.phase})
   end
   return dispatch('Finish','finish',c.count,{phase=c.phase})
  end
  return state=='new' or state=='pending' or state=='done'
 end
 function api:state() return state end
 assert(c.register(function(_,row) assert(api:event(row)) end)==true)
 return api
end
X4LAN_RECOVERY_REGISTRY_WITNESS=M
return M
