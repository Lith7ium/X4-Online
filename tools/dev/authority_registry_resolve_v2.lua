-- Experimental only: MD table and embedded actor conversion are unverified in X4.
-- One owner, one pending request. Import installs nothing and calls no game API.
local M={}
local SCREEN='X4AuthorityRegistryResolveV2'
local function integer(v) return type(v)=='number' and v==v and v>=1 and v<=9007199254740991 and v%1==0 end
local function token(v) return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function finite(v) return type(v)=='number' and v==v and v>=0 and v<math.huge end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and finite(o.timeout) and o.timeout>0 and o.timeout<=300)
 for _,name in ipairs({'issue','clock','valid','key'}) do assert(type(o[name])=='function') end
 local state='idle';local generation={};local busy=false;local pending;local deadline;local last_time
 local seen={};local count=0;local api={}
 local function fail(reason)
  if state~='closed' then state='failed' end
  generation={};pending=nil;deadline=nil
  return false,reason
 end
 local function call(fn,...)
  if busy then return fail('reentrant_callback') end
  local before,phase=generation,state;busy=true
  local ok,value=pcall(fn,...);busy=false
  if before~=generation or phase~=state then return fail('state_changed_in_callback') end
  if not ok then return fail('callback_failed') end
  return true,value
 end
 local function time()
  local ok,v=call(o.clock)
  if not ok then return nil end
  if not finite(v) or (last_time and v<last_time) then fail('invalid_clock');return nil end
  last_time=v;return v
 end
 local function live()
  if state~='pending' then return fail('not_pending') end
  local t=time();if not t then return false,'invalid_clock' end
  if t>=deadline then return fail('timeout') end
  return true
 end
 function api:resolve(request_id,index)
  if state~='idle' then return fail('not_idle') end
  if not token(request_id) or not integer(index) or seen[request_id] or count>=4096 then return fail('invalid_request') end
  local t=time();if not t then return false,'invalid_clock' end
  if state~='idle' then return fail('state_changed') end
  seen[request_id]=true;count=count+1
  pending={request_id=request_id,index=index};deadline=t+o.timeout
  if not finite(deadline) then return fail('invalid_deadline') end
  state='pending';generation={}
  local ok,issued=call(o.issue,SCREEN,'Resolve',{request_id=request_id,epoch=o.epoch,index=index})
  if not ok or issued~=true then return fail('dispatch_uncertain') end
  return live()
 end
 function api:response(row)
  local ok,why=live();if not ok then return false,why end
  if type(row)~='table' or getmetatable(row)~=nil then return fail('invalid_response') end
  for key in pairs(row) do
   if key~='request_id' and key~='epoch' and key~='index' and key~='actor' and key~='status' then return fail('invalid_field') end
  end
  local request_id,epoch,index,actor,status=row.request_id,row.epoch,row.index,row.actor,row.status
  if request_id~=pending.request_id or epoch~=o.epoch or index~=pending.index then return fail('response_mismatch') end
  if status=='unavailable' then
   if actor~=nil and actor~=false and actor~=0 then return fail('invalid_unavailable_actor') end
   return fail('unavailable')
  end
  if status~='ok' or actor==nil or actor==false or actor==0 then return fail('invalid_actor') end
  local good,valid=call(o.valid,actor)
  if not good or valid~=true then return fail('invalid_actor') end
  local keyed,key=call(o.key,actor)
  if not keyed or type(key)~='string' or key=='' or #key>256 then return fail('invalid_actor_key') end
  ok,why=live();if not ok then return false,why end
  local result={request_id=pending.request_id,epoch=o.epoch,index=pending.index,actor=actor,local_key=key}
  pending=nil;deadline=nil;state='idle';generation={}
  return true,result
 end
 function api:tick()
  if state=='pending' then return live() end
  if state=='idle' then return true end
  return false,state
 end
 function api:close() state='closed';pending=nil;deadline=nil;generation={};return true end
 function api:state() return state end
 return api
end
X4LAN_RESOLVE_V2=M
return M
