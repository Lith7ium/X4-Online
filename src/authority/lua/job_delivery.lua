-- Experimental bounded delivery gate. No transport, X4 calls, or handlers on import.
local M={}
local MAX=9007199254740991
local function integer(n) return type(n)=='number' and n==n and n>=1 and n<=MAX and n%1==0 end
local function finite(n) return type(n)=='number' and n==n and n>-math.huge and n<math.huge end
local function hex(s) return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function ident(s) return type(s)=='string' and #s>=1 and #s<=128 and s:match('^[a-zA-Z0-9_]+$')~=nil end
local function peer_id(s) return type(s)=='string' and #s>=1 and #s<=48 and s:match('^[a-zA-Z0-9_-]+$')~=nil end
local function fields(t, allowed)
 if type(t)~='table' or getmetatable(t)~=nil then return false end
 for k in pairs(t) do if not allowed[k] then return false end end
 for k in pairs(allowed) do if rawget(t,k)==nil then return false end end
 return true
end
local PEER={id=true,incarnation=true}
local DESC={macro=true,faction=true,sector_macro=true,x=true,y=true,z=true}
local EVENT={epoch=true,generation=true,sequence=true,index=true,descriptor=true}
local function copy_peer(p)
 if not fields(p,PEER) or not peer_id(p.id) or not hex(p.incarnation) then return nil end
 return {id=p.id,incarnation=p.incarnation}
end
local function copy_event(e)
 if not fields(e,EVENT) or not hex(e.epoch) or not hex(e.generation) or not integer(e.sequence) or not integer(e.index) or not fields(e.descriptor,DESC) then return nil end
 local d=e.descriptor
 if not ident(d.macro) or not ident(d.faction) or not ident(d.sector_macro) or not finite(d.x) or not finite(d.y) or not finite(d.z) then return nil end
 return {epoch=e.epoch,generation=e.generation,sequence=e.sequence,index=e.index,descriptor={macro=d.macro,faction=d.faction,sector_macro=d.sector_macro,x=d.x,y=d.y,z=d.z}}
end
local function equal_event(a,b)
 if not b or a.epoch~=b.epoch or a.generation~=b.generation or a.sequence~=b.sequence or a.index~=b.index then return false end
 for key in pairs(DESC) do if a.descriptor[key]~=b.descriptor[key] then return false end end
 return true
end
local function snapshot(list)
 if type(list)~='table' or getmetatable(list)~=nil or #list<1 or #list>16 then return nil end
 local n=#list;for k in pairs(list) do if not integer(k) or k>n then return nil end end
 local out,ordered,incarnations={},{},{}
 for i=1,n do
  local p=copy_peer(list[i]);if not p or out[p.id] or incarnations[p.incarnation] then return nil end
  out[p.id]=p.incarnation;incarnations[p.incarnation]=true;ordered[i]=p
 end
 return out,ordered
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(type(o.membership)=='function' and type(o.send)=='function' and type(o.release)=='function' and type(o.clock)=='function')
 assert(hex(o.generation),'fresh queue generation required')
 local generation=o.generation
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=300)
 local state,busy='idle',false
 local event,expected,ordered,seen,deadline,lastclock=nil,nil,nil,nil,nil,nil
 local last_epoch,last_sequence=nil,nil
 local function fail(reason) state='failed';return false,reason end
 local function now()
  local previous=state
  local ok,t=pcall(o.clock)
  if not ok or state~=previous or not finite(t) or (lastclock and t<lastclock) then return nil end
  lastclock=t;return t
 end
 local function check()
  local previous=state
  local t=now();if not t or t>=deadline then return false end
  local ok,raw=pcall(o.membership);if not ok or state~=previous then return false end
  local members=snapshot(raw);if not members then return false end
  for id,inc in pairs(expected) do if members[id]~=inc then return false end end
  for id,inc in pairs(members) do if expected[id]~=inc then return false end end
  t=now();return t~=nil and t<deadline
 end
 local api={}
 function api:state() return state end
 function api:begin(raw)
  if busy or state~='idle' then return fail('busy_or_unavailable') end
  busy=true;state='starting'
  local e=copy_event(raw);local t=now()
  local ok,list=pcall(o.membership);local members,peers
  if ok and state=='starting' then members,peers=snapshot(list) end
  if not e or e.generation~=generation or not t or not members or state~='starting' or
   (last_epoch and (e.epoch~=last_epoch or last_sequence>=MAX or e.sequence~=last_sequence+1)) then
   busy=false;return fail('invalid_event_or_membership')
  end
  event,expected,ordered,seen,deadline=e,members,peers,{},t+o.timeout
  if not finite(deadline) then busy=false;return fail('invalid_deadline') end
  state='dispatching'
  for _,p in ipairs(ordered) do
   if not check() or state~='dispatching' then busy=false;return fail('membership_or_deadline') end
   local good,sent=pcall(o.send,copy_peer(p),copy_event(event))
   if not good or sent~=true or state~='dispatching' or not check() then busy=false;return fail('send_unconfirmed') end
  end
  state='waiting';busy=false;return true
 end
 function api:ack(rawpeer,rawevent)
  if busy or (state~='waiting' and state~='released') then return fail('unexpected_ack') end
  busy=true
  local p,e=copy_peer(rawpeer),copy_event(rawevent)
  if not p or expected[p.id]~=p.incarnation or not equal_event(event,e) or not check() then busy=false;return fail('invalid_ack_or_membership') end
  if seen[p.id] then busy=false;return true,'duplicate' end
  if state~='waiting' then busy=false;return fail('unexpected_ack') end
  seen[p.id]=true
  for id in pairs(expected) do if not seen[id] then busy=false;return true,'pending' end end
  state='releasing'
  if not check() or state~='releasing' then busy=false;return fail('membership_or_deadline') end
  local good,result=pcall(o.release,event.epoch,event.sequence,event.index)
  if not good or result~=true or state~='releasing' or not check() then busy=false;return fail('source_release_unconfirmed') end
  state='released';busy=false;return true,'released'
 end
 function api:tick()
  if busy or (state~='waiting' and state~='released') then return fail('unexpected_tick') end
  busy=true;local ok=check();busy=false
  if not ok then return fail('membership_or_deadline') end
  return true,state
 end
 function api:source_acked(epoch,sequence,index)
  if busy or state~='released' then return fail('unexpected_source_ack') end
  busy=true
  if epoch~=event.epoch or sequence~=event.sequence or index~=event.index or not check() then busy=false;return fail('invalid_source_ack') end
  last_epoch,last_sequence=event.epoch,event.sequence
  event,expected,ordered,seen,deadline=nil,nil,nil,nil,nil
  state='idle';busy=false;return true
 end
 return api
end
X4LAN_AUTHORITY_JOB_DELIVERY=M
return M
