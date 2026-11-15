-- Opt-in local adapter for the experimental X4AuthorityShipRegistry MD cue.
-- No game calls, callbacks, retries, networking or installation on import.
--
-- IMPORTANT: MD replies have no request ID. One outstanding request prevents
-- ordinary overlap, but a delayed duplicate reply of the same kind can be
-- mistaken for a subsequent request's reply. This adapter cannot reliably
-- correlate all replies and is not a production correlation protocol.
local M = {}
local SCREEN = 'X4AuthorityShipRegistry'
local MAX = 9007199254740991

local function integer(n, minimum)
 return type(n)=='number' and n==n and n>=minimum and n<=MAX and n%1==0
end
local function finite(n)
 return type(n)=='number' and n==n and n~=math.huge and n~=-math.huge
end
local function key_ok(v)
 return type(v)=='string' and #v>0 and #v<=256
end

-- issue(screen, control, args), key(actor), to_md_actor(actor, key),
-- valid(actor), clock(), and complete(operation, result) are supplied by the
-- caller. Actor keys and resolved actors are local only, never wire identities.
-- complete receives an actor for resolve, an index for enroll, the epoch for
-- initialize, and {epoch=...,count=...} for status. No callback means no
-- accepted result. Any uncertain dispatch or unexpected event faults the
-- instance. A fresh adapter alone cannot fence late events from the old one.
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(type(o.epoch)=='string' and #o.epoch==32 and o.epoch:match('^[0-9a-f]+$'), 'invalid epoch')
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=300, 'invalid timeout')
 for _,name in ipairs({'issue','key','to_md_actor','valid','clock','complete'}) do
  assert(type(o[name])=='function', name..' required')
 end
 local state,pending,deadline,last_clock,seen_epoch='idle',nil,nil,nil,false
 local issuing=false
 local generation={}
 local in_callback=false
 local pending_actor,pending_key=nil,nil
 local api={}
 local function stop(reason)
  if state~='closed' then state='failed' end
  generation={}
  pending,deadline,pending_actor,pending_key=nil,nil,nil,nil
  return false,reason
 end
 -- An injected function may re-enter any public method. Check both state and
 -- this local generation after every call, including calls that return success.
 local function invoke(fn,...)
  if in_callback then stop('reentrant_callback');return false,nil end
  local previous,previous_state,previous_pending=generation,state,pending
  in_callback=true
  local ok,value=pcall(fn,...)
  in_callback=false
  if generation~=previous or state~=previous_state or pending~=previous_pending then
   stop('state_changed_in_callback');return false,nil
  end
  if not ok then return false,nil end
  return true,value
 end
 local function now()
  local ok,value=invoke(o.clock)
  if not ok or not finite(value) or value<0 or (last_clock and value<last_clock) then return nil end
  last_clock=value;return value
 end
 local function check_deadline()
  local value=now()
  if not value then return stop('invalid_clock') end
  if (state=='pending' or state=='delivering') and value>=deadline then return stop('timeout') end
  return true,value
 end
 local function actor_key(actor)
  local ok,valid=invoke(o.valid,actor)
  if not ok or valid~=true then return nil end
  local good,key=invoke(o.key,actor)
  if not good or not key_ok(key) then return nil end
  return key
 end
 local function convert(actor,key)
  local ok,converted=invoke(o.to_md_actor,actor,key)
  if not ok or converted==nil or converted==false or converted==0 then return nil end
  local good,converted_key=invoke(o.key,converted)
  if not good or converted_key~=key or actor_key(actor)~=key then return nil end
  return converted
 end
 local function begin(op,args,actor,key)
  if state~='idle' then return stop('not_idle') end
  local ok,t=check_deadline();if not ok then return false,t end
  if state~='idle' then return stop('state_changed_before_dispatch') end
  pending,deadline,state=op,t+o.timeout,'pending'
  generation={}
  if not finite(deadline) then return stop('invalid_deadline') end
  pending_actor,pending_key=actor,key
  issuing=true
  local good,issued=invoke(o.issue,SCREEN,op,args)
  issuing=false
  if not good or issued~=true then return stop('dispatch_uncertain') end
  if state~='pending' or pending~=op then return stop('state_changed_during_dispatch') end
  local within,reason=check_deadline();if not within then return false,reason end
  if state~='pending' or pending~=op then return stop('state_changed_after_dispatch') end
  return true
 end
 local function finish(op,value)
  if state~='pending' or pending~=op then return stop('state_changed_before_completion') end
  local within,reason=check_deadline();if not within then return false,reason end
  if state~='pending' or pending~=op then return stop('state_changed_before_completion') end
  state='delivering'
  generation={}
  local ok,result=invoke(o.complete,op,value)
  if not ok or result~=true or state~='delivering' then return stop('completion_failed') end
  within,reason=check_deadline();if not within then return false,reason end
  if state~='delivering' or pending~=op then return stop('state_changed_after_completion') end
  pending,deadline,pending_actor,pending_key=nil,nil,nil,nil
  state='idle';generation={};return true
 end
 function api:initialize() return begin('Initialize',{epoch=o.epoch}) end
 function api:status() seen_epoch=false;return begin('Status',{}) end
 function api:enroll(actor)
  if state~='idle' then return stop('not_idle') end
  local key=actor_key(actor)
  if not key then return stop('invalid_actor') end
  local converted=convert(actor,key)
  if not converted then return stop('conversion_failed') end
  return begin('Enroll',{epoch=o.epoch,ship=converted},actor,key)
 end
 function api:resolve(index)
  if not integer(index,1) then return stop('invalid_index') end
  return begin('Resolve',{epoch=o.epoch,index=index})
 end
 function api:on_event(name,value)
  if state~='pending' then return stop('unexpected_event') end
  if issuing then return stop('event_during_dispatch') end
  local ok,reason=check_deadline();if not ok then return false,reason end
  if name=='Refused' or name=='Unavailable' or name=='Faulted' or name=='Uninitialized' then
   return stop('registry_'..name)
  elseif pending=='Initialize' and name=='Initialized' and value==o.epoch then
   return finish(pending,value)
  elseif pending=='Status' and name=='Epoch' and not seen_epoch and value==o.epoch then
   seen_epoch=true;return true
  elseif pending=='Status' and name=='Count' and seen_epoch and integer(value,0) then
   return finish(pending,{epoch=o.epoch,count=value})
  elseif pending=='Enroll' and name=='Enrolled' and integer(value,1) then
   local actor,key=pending_actor,pending_key
   if actor_key(actor)~=key or state~='pending' or pending~='Enroll' then return stop('actor_changed') end
   return finish('Enroll',value)
  elseif pending=='Resolve' and name=='Actor' then
   local key=actor_key(value)
   if not key or not convert(value,key) or state~='pending' or pending~='Resolve' then return stop('invalid_actor') end
   return finish('Resolve',value)
  end
  return stop('unexpected_event')
 end
 function api:tick()
  if state=='failed' or state=='closed' then return false,state end
  local ok,reason=check_deadline();if not ok then return false,reason end
  return true
 end
 function api:close()
  state='closed';generation={};pending,deadline,pending_actor,pending_key=nil,nil,nil,nil
  return true
 end
 function api:state() return state end
 return api
end
return M
