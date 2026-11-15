-- Disposable string-correlation experiment; MD actor formatting is unverified.
local ffi=require('ffi')
local M={};local SCREEN='X4AuthorityRegistryResolveString'
local function token(s) return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function integer(v) return type(v)=='number' and v==v and v>=1 and v<=9007199254740991 and v%1==0 end
local function finite(v) return type(v)=='number' and v==v and v>=0 and v<math.huge end
-- Convert an already returned local ID without accepting a possibly rounded
-- Lua number. The caller must compare this with an independent FFI ID.
function M.actor_u64(v)
 if type(v)=='cdata' and ffi.istype('uint64_t',v) then
  local value=ffi.new('uint64_t',v)
  if value~=ffi.new('uint64_t',0) then return value end
 elseif type(v)=='number' and v==v and v>=1 and v<=9007199254740991 and v%1==0 then
  return ffi.new('uint64_t',v)
 end
 return nil
end
function M.parse_hex(text)
 if type(text)~='string' then return nil end
 if text:sub(1,2)~='0x' and text:sub(1,2)~='0X' then return nil end
 text=text:sub(3)
 if #text<1 or #text>16 or not text:match('^[0-9a-fA-F]+$') then return nil end
 local value=ffi.new('uint64_t',0);local base=ffi.new('uint64_t',16)
 for i=1,#text do
  local c=text:byte(i);local n
  if c>=48 and c<=57 then n=c-48 elseif c>=65 and c<=70 then n=c-55 else n=c-87 end
  value=value*base+ffi.new('uint64_t',n)
 end
 if value==ffi.new('uint64_t',0) then return nil end
 return value
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and finite(o.timeout) and o.timeout>0 and o.timeout<=300)
 for _,n in ipairs({'issue','clock','expected_actor','valid'}) do assert(type(o[n])=='function') end
 local state='idle';local pending,deadline,last=nil,nil,nil;local generation={};local busy=false
 local used={};local count=0;local api={}
 local function fail(reason)
  if state~='closed' then state='failed' end
  pending,deadline=nil,nil;generation={};return false,reason
 end
 local function call(fn,...)
  if busy then return fail('reentrant') end
  local before,phase=generation,state;busy=true;local ok,v=pcall(fn,...);busy=false
  if before~=generation or phase~=state then return fail('state_changed') end
  if not ok then return fail('callback_failed') end
  return true,v
 end
 local function time()
  local ok,v=call(o.clock);if not ok then return nil end
  if not finite(v) or (last and v<last) then fail('clock');return nil end
  last=v;return v
 end
 local function live()
  if state~='pending' then return fail('not_pending') end
  local t=time();if not t then return false,'clock' end
  if t>=deadline then return fail('timeout') end
  return true
 end
 function api:resolve(request_id,index)
  if state~='idle' then return fail('not_idle') end
  if not token(request_id) or not integer(index) or used[request_id] or count>=4096 then return fail('request') end
  local t=time();if not t then return false,'clock' end
  used[request_id]=true;count=count+1;pending={id=request_id,index=index};deadline=t+o.timeout
  if not finite(deadline) then return fail('deadline') end
  state='pending';generation={}
  local ok,issued=call(o.issue,SCREEN,'Resolve',{request_id=request_id,epoch=o.epoch,index=index})
  if not ok or issued~=true then return fail('dispatch') end
  return live()
 end
 function api:response(row)
  local ok,why=live();if not ok then return false,why end
  if type(row)~='string' or #row>160 then return fail('response') end
  local id,epoch,index,status,actor=row:match('^([0-9a-f]+)|([0-9a-f]+)|([0-9]+)|([a-z]+)|([^|]+)$')
  if id~=pending.id or epoch~=o.epoch or index~=string.format('%.0f',pending.index) then return fail('mismatch') end
  if status=='unavailable' then if actor~='0' then return fail('unavailable_actor') end;return fail('unavailable') end
  if status~='ok' then return fail('status') end
  local parsed=M.parse_hex(actor);if not parsed then return fail('actor_hex') end
  local expected_ok,expected=call(o.expected_actor)
  if not expected_ok or type(expected)~='cdata' or not ffi.istype('uint64_t',expected) or expected~=parsed then return fail('actor_mismatch') end
  local valid_ok,valid=call(o.valid,expected)
  if not valid_ok or valid~=true then return fail('invalid_actor') end
  ok,why=live();if not ok then return false,why end
  local result={request_id=pending.id,epoch=o.epoch,index=pending.index}
  pending,deadline=nil,nil;state='idle';generation={};return true,result
 end
 function api:tick() if state=='pending' then return live() elseif state=='idle' then return true end;return false,state end
 function api:close() state='closed';pending,deadline=nil,nil;generation={};return true end
 function api:state() return state end
 return api
end
X4LAN_RESOLVE_STRING=M
return M
