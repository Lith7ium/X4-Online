-- Disabled-by-default local diagnostic. No X4 calls or callbacks on import.
-- A trusted driver serializes all requests and dispatches named MD responses.
local M = {}
local MAX = 9007199254740991
local function integer(n)
 return type(n)=='number' and n==n and n>=1 and n<=MAX and n%1==0
end

function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil, 'disabled' end
 assert(type(o.epoch)=='string' and #o.epoch==32 and o.epoch:match('^[0-9a-f]+$'))
 assert(type(o.last)=='number' and o.last>=0 and o.last<=MAX and o.last%1==0)
 assert(type(o.baseline)=='table' and type(o.issue)=='function' and type(o.key)=='function' and type(o.to_md_actor)=='function'
  and type(o.valid)=='function' and type(o.report)=='function')
 assert(o.expose_actor==nil or type(o.expose_actor)=='boolean')
 assert(o.defer_ack==nil or type(o.defer_ack)=='boolean')
 local known,indices={},{}
 for actor_key,index in pairs(o.baseline) do
  assert(type(actor_key)=='string' and actor_key~='' and integer(index) and index<=o.last and not indices[index])
  known[actor_key]=index;indices[index]=actor_key
 end
 local last=o.last
 local state,sequence,actor,actor_key,index='idle',nil,nil,nil,nil
 local reporting=false
 local last_sequence=0
 local function stop(reason)
  if state~='failed' then
   state='failed'
   -- The caller must fence the queue and discard this diagnostic even if
   -- Abort cannot be delivered. This is not network-delivery confirmation.
   pcall(o.issue,'X4AuthorityJobShipEvents','Abort',{epoch=o.epoch})
  end
  return false,reason
 end
 local function send(screen,op,args)
  local ok,result=pcall(o.issue,screen,op,args)
  if not ok or result~=true then return stop('request_failed') end
  return true
 end
 local function current_actor()
  local before,seq,idx=state,sequence,index
  local ok,value=pcall(o.key,actor)
  if not ok or state~=before or sequence~=seq or index~=idx or type(value)~='string' or value=='' or value~=actor_key then return false end
  local success,valid=pcall(o.valid,actor)
  return success and state==before and sequence==seq and index==idx and valid==true
 end
 local api={}
 function api:front()
  if state~='idle' then return stop('concurrent_request') end
  state='sequence'
  return send('X4AuthorityJobShipEvents','Front',{epoch=o.epoch})
 end
 function api:timeout() return stop('timeout') end
 function api:state() return state end
 -- The owner must independently validate every required client's receipt.
 -- This interface is not itself an ACK collector or a network protocol.
 function api:confirm_delivery(epoch,seq,idx)
  if reporting or not o.defer_ack or state~='await_delivery' or epoch~=o.epoch or
     seq~=sequence or idx~=index or not current_actor() then return stop('invalid_delivery_confirmation') end
  if state~='await_delivery' or seq~=sequence or idx~=index then return stop('state_changed_during_delivery_confirmation') end
  state='ack'
  local sent,reason=send('X4AuthorityJobShipEvents','Ack',{epoch=o.epoch,sequence=sequence,index=index})
  if not sent then return false,reason end
  if state~='ack' then return stop('state_changed_during_ack_dispatch') end
  return true
 end
 function api:event(name,value)
  if state=='failed' then return false,'faulted' end
  if name=='Faulted' or name=='Refused' or name=='Unavailable' then return stop('remote_fault') end
  if state=='sequence' and name=='Empty' then state='idle';return true end
  if state=='sequence' and name=='Sequence' then
   if not integer(value) or value~=last_sequence+1 then return stop('sequence_gap') end
   sequence=value;state='actor';return true
  end
  if state=='actor' and name=='Actor' then
   actor=value
   local ok,k=pcall(o.key,actor)
   if not ok or state~='actor' or type(k)~='string' or k=='' then return stop('actor_unavailable') end
   actor_key=k
   if not current_actor() then return stop('actor_unavailable') end
   local converted,md_actor=pcall(o.to_md_actor,actor,actor_key)
   if not converted or state~='actor' or md_actor==nil or md_actor==false or md_actor==0 then return stop('actor_conversion_failed') end
   local roundtrip,md_key=pcall(o.key,md_actor)
   if not roundtrip or state~='actor' or md_key~=actor_key or not current_actor() or state~='actor' then return stop('actor_conversion_mismatch') end
   -- Enroll can allocate before reporting its index. At the exact-integer
   -- boundary refuse even known actors, before any registry mutation attempt.
   if last>=MAX then return stop('index_capacity') end
   state='enroll'
   return send('X4AuthorityShipRegistry','Enroll',{epoch=o.epoch,ship=md_actor})
  end
  if state=='enroll' and name=='Enrolled' then
   if not integer(value) or not current_actor() then return stop('invalid_enrollment') end
   if known[actor_key] and known[actor_key]~=value then return stop('actor_index_changed') end
   if indices[value] and indices[value]~=actor_key then return stop('index_collision') end
   if value>last and value~=last+1 then return stop('index_gap') end
   index=value
   if o.defer_ack then
    local classification=known[actor_key] and 'previously_observed' or
     (index<=last and 'previously_unobserved_existing_index' or 'new_registry_entry')
    local row={epoch=o.epoch,sequence=sequence,index=index,classification=classification,
     delivery_confirmed=false,birth_confirmed=false}
    state='await_delivery';reporting=true
    local ok,accepted
    if o.expose_actor==true then ok,accepted=pcall(o.report,row,actor)
    else ok,accepted=pcall(o.report,row) end
    reporting=false
    if not ok or accepted~=true or state~='await_delivery' then return stop('report_failed') end
    return true
   end
   state='ack'
   return send('X4AuthorityJobShipEvents','Ack',{epoch=o.epoch,sequence=sequence,index=index})
  end
  if state=='ack' and name=='Acked' then
   if value~=sequence or not current_actor() then return stop('invalid_ack') end
   local classification
   if known[actor_key] then classification='previously_observed'
   elseif index<=last then classification='previously_unobserved_existing_index'
   else classification='new_registry_entry';last=index end
   known[actor_key]=index;indices[index]=actor_key;last_sequence=sequence
   local row={epoch=o.epoch,sequence=sequence,index=index,
    classification=classification,delivery_confirmed=false,birth_confirmed=false}
   if not o.defer_ack then
    local ok,accepted
    reporting=true
    if o.expose_actor==true then ok,accepted=pcall(o.report,row,actor)
    else ok,accepted=pcall(o.report,row) end
    reporting=false
    if not ok or accepted~=true or state~='ack' then return stop('report_failed') end
   end
   sequence,actor,actor_key,index=nil,nil,nil,nil;state='idle';return true
  end
  return stop('unexpected_event')
 end
 return api
end
X4LAN_AUTHORITY_JOB_REGISTRY_PROBE=M
return M
