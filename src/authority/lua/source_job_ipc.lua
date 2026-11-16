-- Experimental source-side adapter; caller owns sockets, UI loop and X4 host.
local M={}
local MAX=9007199254740991
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function natural(v)return type(v)=='number' and v==v and v>=1 and v<=MAX and v%1==0 end
local function finite(v)return type(v)=='number' and v==v and v>-math.huge and v<math.huge end
local function name(v)return type(v)=='string' and #v>=1 and #v<=128 and v:match('^[a-zA-Z0-9_]+$')~=nil end
local function split(s)local out={};for v in (s..'|'):gmatch('(.-)|')do out[#out+1]=v end;return out end
local function fields(t,keys)
 if type(t)~='table' or getmetatable(t)~=nil then return false end
 for k in pairs(t)do if not keys[k]then return false end end
 for k in pairs(keys)do if rawget(t,k)==nil then return false end end
 return true
end
local EVENT={epoch=true,generation=true,sequence=true,index=true,descriptor=true}
local DESC={macro=true,faction=true,sector_macro=true,x=true,y=true,z=true}
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.lease) and token(o.attempt) and token(o.epoch) and token(o.generation))
 assert(o.lease~=o.attempt and o.lease~=o.epoch and o.lease~=o.generation and o.attempt~=o.epoch and o.attempt~=o.generation and o.epoch~=o.generation)
 assert(type(o.gate)=='table' and type(o.gate.new)=='function' and type(o.guard)=='function' and type(o.clock)=='function' and type(o.send)=='function' and type(o.release)=='function')
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=300)
 local phase,busy='idle',false;local event,members,gate,deadline,last_clock,next_peer=nil,nil,nil,nil,nil,nil
 local last_seq=0
 local function fail(reason)phase='failed';return false,reason end
 local function check()
  if phase=='failed' then return false end
  local before=phase;local ok,t=pcall(o.clock)
  if not ok or phase~=before or not finite(t) or (last_clock and t<last_clock) or (deadline and t>=deadline) then return false end
  last_clock=t;local g,result=pcall(o.guard)
  if not g or result~=true or phase~=before then return false end
  local again,after=pcall(o.clock)
  if not again or phase~=before or not finite(after) or after<t or (deadline and after>=deadline) then return false end
  last_clock=after;return true
 end
 local function emit(parts)
  if not check()then return false end
  local raw=table.concat({'S',o.lease,o.attempt,unpack(parts)},'|')
  if #raw>4096 then return false end
  local ok,result=pcall(o.send,raw)
  return ok and result==true and check()
 end
 local function identity()return {event.epoch,event.generation,string.format('%.0f',event.sequence),string.format('%.0f',event.index)}end
 local api={}
 function api:state()return phase end
 function api:candidate(e)
  if busy or phase~='idle' then return fail('unexpected_candidate') end
  busy=true
  local ok=fields(e,EVENT) and fields(e.descriptor,DESC) and e.epoch==o.epoch and e.generation==o.generation and
   natural(e.sequence) and e.sequence==last_seq+1 and natural(e.index) and name(e.descriptor.macro) and
   name(e.descriptor.faction) and name(e.descriptor.sector_macro) and finite(e.descriptor.x) and finite(e.descriptor.y) and finite(e.descriptor.z)
  if not ok then busy=false;return fail('invalid_candidate')end
  local d=e.descriptor;event={epoch=e.epoch,generation=e.generation,sequence=e.sequence,index=e.index,
   descriptor={macro=d.macro,faction=d.faction,sector_macro=d.sector_macro,x=d.x,y=d.y,z=d.z}}
  if not check()then busy=false;return fail('invalid_candidate')end
  d=event.descriptor
  deadline=last_clock+o.timeout;phase='await_bind'
  local parts={'CANDIDATE',unpack(identity())};parts[#parts+1]=d.macro;parts[#parts+1]=d.faction;parts[#parts+1]=d.sector_macro
  for _,k in ipairs({'x','y','z'})do parts[#parts+1]=string.format('%.17g',d[k])end
  local sent=emit(parts);busy=false
  if not sent then return fail('candidate_send')end;return true
 end
 function api:packet(raw)
  if busy or (phase~='await_bind' and phase~='waiting' and phase~='await_rearm') then
   return fail('unexpected_packet')
  end
  busy=true
  if type(raw)~='string' or #raw>4096 or not check() then
   busy=false
   return fail('invalid_packet')
  end
  local parts=split(raw)
  local event_identity=identity()
  if parts[1]~='P' or parts[2]~=o.lease or parts[3]~=o.attempt or
     parts[5]~=event_identity[1] or parts[6]~=event_identity[2] or
     parts[7]~=event_identity[3] or parts[8]~=event_identity[4] then
   busy=false
   return fail('foreign_packet')
  end
  if phase=='await_rearm' and parts[4]=='REARM' and #parts==8 then
   if not emit({'REARMED',event_identity[1],event_identity[2],event_identity[3],event_identity[4]}) then
    busy=false
    return fail('rearm_send')
   end
   last_seq=event.sequence
   event,members,gate,deadline,next_peer=nil,nil,nil,nil,nil
   phase='idle'
   busy=false
   return true
  elseif phase=='await_bind' and parts[4]=='BIND' then
   local member_count=tonumber(parts[9])
   if not natural(member_count) or member_count>16 or parts[9]~=string.format('%.0f',member_count) or
      #parts~=9+2*member_count then
    busy=false
    return fail('invalid_members')
   end
   members={}
   local seen,incarnations={},{}
   for index=1,member_count do
    local peer,incarnation=parts[8+2*index],parts[9+2*index]
    if not peer:match('^peer_[1-9]%d*$') or #peer>48 or not token(incarnation) or
       seen[peer] or incarnations[incarnation] then
     busy=false
     return fail('invalid_members')
    end
    members[index]={id=peer,incarnation=incarnation}
    seen[peer]=true
    incarnations[incarnation]=true
   end
   local announced=0
   local created,built=pcall(o.gate.new,{
    enabled=true,generation=o.generation,timeout=o.timeout,clock=o.clock,
    membership=function()return members end,
    send=function(peer)
     announced=announced+1
     return members[announced] and peer.id==members[announced].id and
      peer.incarnation==members[announced].incarnation
    end,
    release=function(epoch,sequence,index)return o.release(epoch,sequence,index)end,
   })
   if not created or type(built)~='table' or phase~='await_bind' then
    busy=false
    return fail('gate_create')
   end
   gate=built
   local called,started=pcall(gate.begin,gate,event)
   if not called or not started or announced~=#members or phase~='await_bind' then
    busy=false
    return fail('gate_begin')
   end
   next_peer=1
   phase='waiting'
   local sent=emit({'READY',unpack(event_identity)})
   busy=false
   if not sent then return fail('ready_send') end
   return true
  elseif phase=='waiting' and parts[4]=='RECEIPT' and #parts==10 then
   local peer=members[next_peer]
   if not peer or parts[9]~=peer.id or parts[10]~=peer.incarnation then
    busy=false
    return fail('foreign_receipt')
   end
   local called,accepted,status=pcall(gate.ack,gate,peer,event)
   if not called or not accepted or not check() then
    busy=false
    return fail('gate_ack')
   end
   next_peer=next_peer+1
   if status=='pending' and next_peer<=#members then
    local sent=emit({'PARTIAL',event_identity[1],event_identity[2],event_identity[3],event_identity[4],peer.id,peer.incarnation})
    busy=false
    if not sent then return fail('partial_send') end
    return true
   end
   if status~='released' or next_peer~=#members+1 then
    busy=false
    return fail('gate_release')
   end
   phase='await_source_ack'
   busy=false
   return true
  end
  busy=false
  return fail('unexpected_packet')
 end
 function api:source_acked(epoch,sequence,index)
  if busy or phase~='await_source_ack' or not check() or epoch~=event.epoch or
     sequence~=event.sequence or index~=event.index then
   return fail('invalid_source_ack')
  end
  busy=true
  local event_identity=identity()
  local peer=members[#members]
  local called,accepted=pcall(gate.source_acked,gate,epoch,sequence,index)
  if not called or not accepted or not check() then
   busy=false
   return fail('gate_source_ack')
  end
  if not emit({'SOURCE_ACKED',event_identity[1],event_identity[2],event_identity[3],event_identity[4],peer.id,peer.incarnation}) then
   busy=false
   return fail('source_ack_send')
  end
  phase='await_rearm'
  busy=false
  return true
 end
 function api:tick()
  if busy or phase=='idle' or phase=='failed' then return fail('unexpected_tick')end
  if not check()then return fail('deadline_or_guard')end
  if gate then
   local called,state=pcall(gate.state,gate);if not called then return fail('gate_state')end
   if state=='waiting' or state=='released' then local ok,result=pcall(gate.tick,gate);if not ok or not result then return fail('gate_tick')end end
  end
  return true
 end
 return api
end
X4LAN_AUTHORITY_SOURCE_JOB_IPC=M
return M
