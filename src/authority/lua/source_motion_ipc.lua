-- Default-off source-only IPC; caller owns local UDP socket and X4 update hook.
-- A SAMPLE is not a TCP receipt or a client X4 apply.
local M={}
local MAX=9007199254740991
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function integer(v)return type(v)=='number' and v==v and v>=1 and v<=MAX and v%1==0 end
local function finite(v)return type(v)=='number' and v==v and v~=-math.huge and v~=math.huge end
local function split(v)local a={};for x in (v..'|'):gmatch('(.-)|')do a[#a+1]=x end;return a end
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 local fixed={};for k,v in pairs(c)do fixed[k]=v end;c=fixed
 assert(token(c.lease) and token(c.attempt) and token(c.epoch) and token(c.generation))
 assert(c.lease~=c.attempt and c.lease~=c.epoch and c.lease~=c.generation and c.attempt~=c.epoch and c.attempt~=c.generation and c.epoch~=c.generation)
 assert(finite(c.timeout) and c.timeout>0 and c.timeout<=120)
 assert(type(c.clock)=='function' and type(c.guard)=='function' and type(c.fault)=='function')
 assert(c.stop==nil or type(c.stop)=='function') -- caller owns sampler, bootstrap and event-router shutdown
 assert(c.candidate_enabled==nil or type(c.candidate_enabled)=='boolean')
 assert(c.freeze_drain==nil or type(c.freeze_drain)=='boolean')
 if c.freeze_drain then assert(type(c.net.pending)=='function') end
 if c.candidate_enabled then assert(c.saved_baseline~=nil)end
 if c.saved_baseline~=nil then
  assert(type(c.saved_baseline)=='table' and integer(c.saved_baseline.limit) and type(c.saved_baseline.guard)=='function')
  c.saved_baseline={limit=c.saved_baseline.limit,guard=c.saved_baseline.guard}
 end
 assert((type(c.net)=='table' or type(c.net)=='userdata') and type(c.net.send)=='function' and type(c.net.receive)=='function')
 if c.stop~=nil or c.candidate_enabled then assert(type(c.net.pending)=='function')end
 local state,busy='new',false;local last,deadline,request,seq,saved_index=nil,nil,nil,0,nil
 local candidate_done,candidate_selected=false,nil
 local api={}
 local function fail(reason)if state~='failed' then state='failed';pcall(c.fault,reason)end;return false end
 local function check()
  if state=='failed' then return false end
  local before=state;local ok,t=pcall(c.clock)
  if not ok or state~=before or not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return false end
  last=t;local good,v=pcall(c.guard)
  if not good or v~=true or state~=before then return false end
  if state=='register_saved' then
   local ok,allowed=pcall(c.saved_baseline.guard,c.epoch,c.saved_baseline.limit)
   if not ok or allowed~=true or state~=before then return false end
   local yes,again=pcall(c.guard)
   if not yes or again~=true or state~=before then return false end
  end
  local again,u=pcall(c.clock)
  if not again or state~=before or not finite(u) or u<t or (deadline and u>=deadline)then return false end
  last=u;return true
 end
 local function send(fields)
  if not check() then return false end
  local s=table.concat({'S',c.lease,c.attempt,unpack(fields)},'|')
  if #s>768 then return false end
  local before=state;local ok,v=pcall(c.net.send,c.net,s)
  return ok and v==true and state==before and check()
 end
 local function context(kind)return {kind,c.epoch,c.generation}end
 function api:start()
  if busy or state~='new' then return fail('start')end
  busy=true;local ok=pcall(function()assert(check());deadline=last+c.timeout;state='binding';assert(send(context('HELLO')))end)
  busy=false;if not ok then return fail('start')end;return true
 end
 function api:tick()
  if busy or state=='new' or state=='failed' or state=='stopped' then return fail('tick')end
  busy=true
  local ok=pcall(function()
   assert(check());local packet=c.net:receive();assert(check())
   if packet==nil then return end
   assert(type(packet)=='string' and #packet<=768)
   local p=split(packet)
   assert(p[1]=='P' and p[2]==c.lease and p[3]==c.attempt and p[5]==c.epoch and p[6]==c.generation)
   if state=='binding' then
    assert(#p==6 and p[4]=='BOUND');state='ready';assert(send(context('ATTACHED')));deadline=nil
   elseif state=='ready' or (state=='frozen' and c.freeze_drain) then
    local was_frozen=state=='frozen'
    assert((#p==7 and (p[4]=='PULL' or (c.freeze_drain and (p[4]=='FREEZE' or p[4]=='RESUME')) or (p[4]=='STOP' and c.stop) or
     (p[4]=='CANDIDATE' and c.candidate_enabled and not candidate_done))) or
     (#p==9 and p[4]=='REGISTER_SAVED' and c.saved_baseline))
    assert(p[7]:match('^[1-9]%d*$') and #p[7]<=16)
    local n=tonumber(p[7]);assert(integer(n) and string.format('%.0f',n)==p[7] and n==seq+1)
    assert((was_frozen and p[4]=='RESUME') or (not was_frozen and p[4]~='RESUME'))
    request=n;deadline=last+c.timeout
    if p[4]=='FREEZE' then
     assert(c.freeze_drain and not was_frozen);state='freeze_requested'
    elseif p[4]=='RESUME' then
     assert(c.freeze_drain and was_frozen);state='resume_requested'
    elseif p[4]=='STOP' then
     -- stop() must synchronously close the idle bootstrap, sampler and event
     -- router, or return false. Keep the UDP socket owned until X4 cleanup so
     -- the supervisor can still validate its peer after the acknowledgement.
     state='stopping';assert(check())
     local invoked,closed=pcall(c.stop)
     assert(invoked and closed==true and state=='stopping' and check())
     -- Refuse acknowledgement if any datagram is already queued, including
     -- empty or oversized packets that receive() itself cannot distinguish.
     local checked,queued=pcall(c.net.pending,c.net)
     assert(checked and queued==false and state=='stopping' and check())
     assert(send({'STOPPED',c.epoch,c.generation,string.format('%.0f',request)}))
     seq=request;request=nil;deadline=nil;state='stopped'
    elseif p[4]=='PULL' then
     assert(not c.candidate_enabled or candidate_selected);state='requested'
    elseif p[4]=='CANDIDATE' then state='candidate' else
     assert(p[8]:match('^[1-9]%d*$') and #p[8]<=16 and p[9]==string.format('%.0f',c.saved_baseline.limit))
     saved_index=tonumber(p[8]);assert(integer(saved_index) and saved_index<=c.saved_baseline.limit and string.format('%.0f',saved_index)==p[8])
     assert(not c.candidate_enabled or saved_index==candidate_selected)
     state='register_saved';assert(check())
    end
   else error('unexpected packet')end
  end)
  busy=false;if not ok then return fail('packet')end;return true
 end
 -- FREEZE/RESUME share the existing sequence and local socket ownership.
 -- The session owns draining/reset and is the only caller of completion.
 function api:freeze_request()return state=='freeze_requested' and request or nil end
 function api:resume_request()return state=='resume_requested' and request or nil end
 function api:queue_empty()
  if busy or not c.freeze_drain or (state~='freeze_requested' and state~='resume_requested' and state~='frozen' and state~='ready') then return false end
  local ok,queued=pcall(c.net.pending,c.net)
  return ok and queued==false
 end
 local function complete_barrier(kind,id,expected,next_state)
  if busy or state~=expected or id~=request then return fail('barrier_complete') end
  busy=true;local ok=pcall(function()
   assert(check() and c.net:pending()==false and check())
   assert(send({kind,c.epoch,c.generation,string.format('%.0f',request)}))
   seq=request;request=nil;deadline=nil;state=next_state
  end);busy=false
  if not ok then return fail('barrier_complete') end
  return true
 end
 function api:freeze_complete(id)return complete_barrier('FROZEN',id,'freeze_requested','frozen') end
 function api:resume_complete(id)return complete_barrier('RESUMED',id,'resume_requested','ready') end
 function api:requested()return state=='requested' end
 function api:candidate_requested()return state=='candidate' end
 function api:candidate_complete(result)
  if busy or state~='candidate' or candidate_done then return fail('candidate_complete')end
  busy=true;local ok=pcall(function()
   assert(check() and type(result)=='table' and getmetatable(result)==nil)
   local fields={'CANDIDATE',c.epoch,c.generation,string.format('%.0f',request)}
   if result.status=='candidate' then
    assert(result.epoch==c.epoch and integer(result.index) and result.index<=c.saved_baseline.limit and result.runtime_reservation==false)
    for k in pairs(result)do assert(k=='status' or k=='epoch' or k=='index' or k=='runtime_reservation')end
    candidate_selected=result.index;fields[#fields+1]='candidate';fields[#fields+1]=string.format('%.0f',result.index)
   else
    assert(result.status=='inconclusive' and (result.reason=='no_candidate' or result.reason=='registry_refused' or result.reason=='getter_or_context_unavailable'))
    for k in pairs(result)do assert(k=='status' or k=='reason')end
    fields[#fields+1]='inconclusive';fields[#fields+1]=result.reason
   end
   -- Never acknowledge a result while an already queued follow-up may make
   -- this same frame fail. Continue late-packet checks after the response.
   local checked,queued=pcall(c.net.pending,c.net)
   assert(checked and queued==false and state=='candidate' and check())
   assert(send(fields));candidate_done=true;seq=request;request=nil;deadline=nil;state='ready'
  end);busy=false;if not ok then return fail('candidate_complete')end;return true
 end
 function api:saved_request()return state=='register_saved' and saved_index or nil end
 -- The caller must first complete the correlated bootstrap and sampler register.
 function api:saved_registered(index)
  if busy or state~='register_saved' or index~=saved_index then return fail('complete')end
  busy=true;local ok=pcall(function()
   assert(check());assert(send({'SAVED_REGISTERED',c.epoch,c.generation,string.format('%.0f',request),
    string.format('%.0f',saved_index),string.format('%.0f',c.saved_baseline.limit)}))
   seq=request;request=nil;saved_index=nil;deadline=nil;state='ready'
  end)
  busy=false;if not ok then return fail('complete')end;return true
 end
 function api:complete(sample)
  if busy or state~='requested' then return fail('complete')end
  busy=true;local ok=pcall(function()
   assert(check())
   local fields
   if sample==nil then fields={'NO_SAMPLE',c.epoch,c.generation,string.format('%.0f',request)}
   else
    assert(type(sample)=='table' and getmetatable(sample)==nil and (sample.version==1 or sample.version==2 or sample.version==3) and sample.epoch==c.epoch and sample.generation==c.generation
     and integer(sample.index) and integer(sample.sequence) and type(sample.sector_macro)=='string' and #sample.sector_macro<=128
     and sample.sector_macro:match('^[A-Za-z0-9_]+$') and finite(sample.source_time) and sample.source_time>=0 and sample.source_time<=1e12)
    for _,k in ipairs({'x','y','z'})do assert(finite(sample[k]) and math.abs(sample[k])<=1e7)end
    local real_time = sample.version == 3
    local v = sample.velocity
    if real_time then
     assert(finite(sample.capture_time) and sample.capture_time >= 0 and sample.capture_time <= 1e12)
     local allowed = {version=true,epoch=true,generation=true,index=true,sequence=true,
      sector_macro=true,source_time=true,capture_time=true,x=true,y=true,z=true,real_velocity=true}
     for key in pairs(sample) do assert(allowed[key], 'unexpected real-time sample field') end
     v = sample.real_velocity
     if v ~= nil then
      assert(type(v)=='table' and getmetatable(v)==nil)
      for key in pairs(v) do assert(key=='x' or key=='y' or key=='z', 'unexpected real-time rate field') end
     end
    else
     assert(sample.capture_time == nil and sample.real_velocity == nil, 'mixed motion clock versions')
    end
    if v~=nil then assert(type(v)=='table' and getmetatable(v)==nil);for _,k in ipairs({'x','y','z'})do assert(finite(v[k]) and math.abs(v[k])<=5000)end end
    local angular=sample.angular_rate
    if sample.version==2 then
     local orientation=sample.orientation
     assert(type(orientation)=='table' and getmetatable(orientation)==nil)
     for _,k in ipairs({'yaw','pitch','roll'})do assert(finite(orientation[k]) and math.abs(orientation[k])<=2*math.pi)end
     assert((v==nil)==(angular==nil))
     if angular~=nil then
      assert(type(angular)=='table' and getmetatable(angular)==nil)
      for _,k in ipairs({'yaw','pitch','roll'})do assert(finite(angular[k]) and math.abs(angular[k])<=2*math.pi)end
     end
    else assert(sample.orientation==nil and angular==nil) end
    local sample_kind = real_time and 'SAMPLE3' or (sample.version==2 and 'SAMPLE2' or 'SAMPLE')
    fields={sample_kind,c.epoch,c.generation,string.format('%.0f',request),string.format('%.0f',sample.index),
     string.format('%.0f',sample.sequence),sample.sector_macro,string.format('%.17g',sample.source_time)}
    if real_time then fields[#fields+1] = string.format('%.17g', sample.capture_time) end
    for _,k in ipairs({'x','y','z'})do fields[#fields+1]=string.format('%.17g',sample[k])end
    if sample.version==2 then for _,k in ipairs({'yaw','pitch','roll'})do fields[#fields+1]=string.format('%.17g',sample.orientation[k])end end
    for _,k in ipairs({'x','y','z'})do fields[#fields+1]=v and string.format('%.17g',v[k]) or '-'end
    if sample.version==2 then for _,k in ipairs({'yaw','pitch','roll'})do fields[#fields+1]=angular and string.format('%.17g',angular[k]) or '-'end end
   end
   assert(send(fields));seq=request;request=nil;deadline=nil;state='ready'
  end)
  busy=false;if not ok then return fail('complete')end;return true
 end
 -- After STOP, source activity is disabled but the socket remains owned.
 -- Do not consult the running-world guard: a confirmed pause is now allowed.
 function api:check_stopped()
  if busy or state~='stopped' then return fail('stopped_check')end
  busy=true;local ok,has=pcall(c.net.pending,c.net);busy=false
  if not ok or has~=false or state~='stopped' then return fail('late_packet')end
  return true
 end
 function api:state()return state end
 return api
end
X4LAN_AUTHORITY_SOURCE_MOTION_IPC=M
return M
