-- Default-off local motion bind IPC; one existing UI owner drives start/tick.
-- The optional disposable setter keeps actor handles local; no extra update hook or TCP reader.
local M={};local MAX=9007199254740991
local owners=setmetatable({},{__mode='k'});local registered=false;local external_router=nil
local function token(v,n)return type(v)=='string' and #v==n and v:match('^[0-9a-f]+$')~=nil end
local function integer(v)return type(v)=='number' and v==v and v>=1 and v<=MAX and v%1==0 end
local function natural(v)
 if type(v)~='string' or #v>16 or not v:match('^[1-9]%d*$') then return nil end
 local n=tonumber(v);if not integer(n) or string.format('%.0f',n)~=v then return nil end;return n
end
local function number(v,lo,hi)
 if type(v)~='string' or #v<1 or #v>32 or not v:match('^[%d%.%+%-eE]+$') then return nil end
 local n=tonumber(v);if not n or n~=n or n<lo or n>hi then return nil end;return n
end
local function name(v)return type(v)=='string' and #v>=1 and #v<=128 and v:match('^[A-Za-z0-9_]+$')~=nil end
local function split(v)local p={};for s in (v..'|'):gmatch('(.-)|')do p[#p+1]=s end;return p end
-- Fixed diagnostics only; external callback text never becomes log data.
local playback_stages={}
for word in ('state clock guard paused buffer_reset sample arrival sequence buffer_push read read_pose game_read game_value game_clock readback_record render render_frame observation_record distance write write_state'):gmatch('%S+')do playback_stages[word]=true end
local native_stages={}
for word in ('initial profile profile_recheck references actor sector zone player player_container docking fixture fixture_sector fixture_code validated position_read setter'):gmatch('%S+')do native_stages[word]=true end
local function playback_diagnostic(stage,native_stage)
 return {stage=playback_stages[stage] and stage or 'unknown',native_stage=native_stages[native_stage] and native_stage or 'unknown'}
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 for _,k in ipairs({'lease','attempt','epoch','generation','nonce'})do assert(token(c[k],32),k)end
 assert(c.lease~=c.attempt and c.lease~=c.epoch and c.lease~=c.generation and c.attempt~=c.epoch and c.attempt~=c.generation and c.epoch~=c.generation and c.nonce~=c.lease and c.nonce~=c.attempt and c.nonce~=c.epoch and c.nonce~=c.generation)
 assert(type(c.timeout)=='number' and c.timeout>0 and c.timeout<=30 and type(c.max_age)=='number' and c.max_age>0 and c.max_age<=30)
 assert(integer(c.max_tracks) and c.max_tracks<=100000)
 assert(type(c.buffer)=='table' and type(c.buffer.new)=='function')
 local new_buffer=c.buffer.new
 for _,k in ipairs({'clock','guard','register','factory','fault'})do assert(type(c[k])=='function',k)end
 assert(c.stop==nil or type(c.stop)=='function')
 local saved
 if c.saved_baseline~=nil then
  local s=c.saved_baseline
  assert(type(s)=='table' and s.enabled==true and integer(s.baseline) and type(s.guard)=='function' and
   type(s.register)=='function' and type(s.factory)=='function','invalid saved baseline route')
  saved={baseline=s.baseline,guard=s.guard,register=s.register,factory=s.factory}
 end
 assert(c.audit==nil or type(c.audit)=='function')
 assert((type(c.net)=='table' or type(c.net)=='userdata') and type(c.net.send)=='function' and type(c.net.receive)=='function')
 assert(not owners[c.net],'motion socket already owned');owners[c.net]=true
 local apply=c.saved_apply
 if apply~=nil then
  assert(saved and type(apply)=='table' and apply.enabled==true and type(apply.factory)=='function' and type(apply.register)=='function' and
   (apply.immediate_readback==nil or apply.immediate_readback==true) and
   (apply.observe_limit==nil or (integer(apply.observe_limit) and apply.observe_limit>=2 and apply.observe_limit<=8 and apply.immediate_readback==true)),'invalid saved apply')
  apply={factory=apply.factory,register=apply.register,immediate_readback=apply.immediate_readback,observe_limit=apply.observe_limit}
 end
 local playback=c.saved_playback
 if playback~=nil then
  assert(saved and not apply and type(playback)=='table' and playback.enabled==true and
   type(playback.factory)=='function','invalid saved playback')
 end
 local state,busy='new',false;local last,pending,deadline,delivered=nil,nil,nil,nil
 local staged,bound,writer,operation_identity,apply_used,preflight_ready=nil,nil,nil,nil,false,false
 local operation_requests,operation_count,preflight_attempted={},0,false
 local observe_count,stream_index,stream_sequence,stream_time,stream_binding=0,nil,nil,nil,nil
 local tracks,track_count={},0;local api={}
 local playback_uncertain=false
 local function stop_playback()
  local success=true
  for _,entry in pairs(tracks)do
   if entry.playback then
    local observed,uncertain=pcall(entry.playback.outcome_uncertain,entry.playback)
    playback_uncertain=playback_uncertain or not observed or uncertain==true
    local ok,stopped=pcall(entry.playback.stop,entry.playback)
    success=ok and stopped==true and success
   end
  end
  return success
 end
 local function fail(reason,diagnostic)
  if state~='failed' then
   local retained=diagnostic and playback_diagnostic(diagnostic.stage,diagnostic.native_stage)
   state='failed'
   stop_playback() -- Disable every writer before notifying the enclosing owner.
   pcall(c.fault,reason,playback_uncertain,retained)
  end
  return false
 end
 local function check()
  if state=='failed' then return false end
  local old=state;local ok,t=pcall(c.clock)
  if not ok or state~=old or type(t)~='number' or t~=t or t<0 or t==math.huge or (last and t<last) or (deadline and t>=deadline) then return false end
  last=t;local good,g=pcall(c.guard);if not good or g~=true or state~=old then return false end
  if saved then
   local valid,ok=pcall(saved.guard,c.epoch,saved.baseline)
   if not valid or ok~=true or state~=old then return false end
   local again,still=pcall(c.guard)
   if not again or still~=true or state~=old then return false end
  end
  local yes,u=pcall(c.clock)
  if not yes or state~=old or type(u)~='number' or u~=u or u<t or u==math.huge or (deadline and u>=deadline) then return false end
  last=u;return true
 end
 local function send(text)
  if #text>768 or not check() then return false end
  local old=state;local ok,v=pcall(c.net.send,c.net,text)
  return ok and v==true and state==old and check()
 end
 local function reply(kind,identity)
  local p={'R',c.lease,c.attempt,kind}
  if identity then for _,v in ipairs(identity)do p[#p+1]=v end
  else p[#p+1]=c.epoch;p[#p+1]=c.generation end
  return table.concat(p,'|')
 end
 function api:start()
  if busy or state~='new' then return fail('start')end
  busy=true;local ok=pcall(function()
   assert(check());assert(c.register(function(_,v)api:event(v)end)==true and state=='new')
   if saved then assert(saved.register(function(_,v)api:event(v,'saved')end)==true and state=='new')end
   if apply then assert(apply.register(function(_,v)api:apply_event(v)end)==true and state=='new')end
   state='ready';assert(send(reply('READY')))
  end);busy=false;if not ok then return fail('start')end;return true
 end
 local function accept(raw)
  if type(raw)~='string' or #raw>768 then return false end
  local p=split(raw)
  local full_pose = p[4]=='BIND2'
  if (full_pose and (#p~=24 or apply or playback)) or (not full_pose and (#p~=18 or p[4]~='BIND')) or
     p[1]~='M' or p[2]~=c.lease or p[3]~=c.attempt or
     not token(p[5],32) or p[6]~=c.epoch or p[7]~=c.generation or not name(p[10]) or not token(p[11],64) then return false end
  local index,seq=natural(p[8]),natural(p[9]);if not index or not seq then return false end
  local t=number(p[12],0,1e12);local x,y,z=number(p[13],-1e7,1e7),number(p[14],-1e7,1e7),number(p[15],-1e7,1e7)
  if not t or not x or not y or not z then return false end
  if apply and apply.observe_limit then
   if observe_count>=apply.observe_limit or index>saved.baseline or
    (stream_index and (index~=stream_index or seq<=stream_sequence or t<=stream_time)) then return false end
  end
  local pose={x,y,z}
  if full_pose then
   for i=16,18 do
    local angle=number(p[i],-2*math.pi,2*math.pi);if not angle then return false end
    pose[#pose+1]=angle
   end
  end
  local rate
  local rate_start=full_pose and 19 or 16
  if p[rate_start]=='-' and p[rate_start+1]=='-' and p[rate_start+2]=='-' then
   if full_pose and (p[22]~='-' or p[23]~='-' or p[24]~='-') then return false end
   rate=nil
  else
   local vx,vy,vz=number(p[rate_start],-5000,5000),number(p[rate_start+1],-5000,5000),number(p[rate_start+2],-5000,5000)
   if not vx or not vy or not vz then return false end;rate={vx,vy,vz}
   if full_pose then
    for i=22,24 do
     local angular_rate=number(p[i],-2*math.pi,2*math.pi);if not angular_rate then return false end
     rate[#rate+1]=angular_rate
    end
   end
  end
  if not check() then return false end
  if apply and apply.observe_limit then stream_index=index;stream_sequence=seq;stream_time=t end
  local arrival=last
  local entry=tracks[index]
  if entry and (entry.sector~=p[10] or entry.dimensions~=#pose) then return false end
  if not entry then
   if track_count>=c.max_tracks then return false end
   track_count=track_count+1
   local nonce=c.nonce -- full 128-bit owner nonce; binding adds index and request counter
   local route=saved and index<=saved.baseline and 'saved' or 'replica'
   local factory=route=='saved' and saved.factory or c.factory
   local binding=assert(factory({capture_binding=(apply or playback) and function(actor,sector,zone,idx,sequence)
     if state~='pending' or not pending or pending.route~='saved' or idx~=pending.index or sequence~=pending.sequence or staged then return false end
     if type(actor)~='string' or type(sector)~='string' or type(zone)~='string' then return false end
     staged={actor_key=actor,sector_key=sector,zone_key=zone,index=idx,sequence=sequence};return true
    end or nil,epoch=c.epoch,generation=c.generation,index=index,sector_macro=p[10],nonce=nonce,
    timeout=c.timeout,max_age=c.max_age,complete=function(result)
     if state~='pending' or delivered or not pending or type(result)~='table' or result.epoch~=c.epoch or
        result.generation~=c.generation or result.index~=pending.index or result.sequence~=pending.sequence or result.sector_macro~=pending.sector then return false end
     delivered=true;return true
    end}))
   if state~='ready' or not check() then return false end
   local buffer
   if not playback then
    buffer=assert(new_buffer({dimensions=#pose,hold_only=true}))
    if type(buffer)~='table' or type(buffer.push)~='function' or state~='ready' or not check() then return false end
   elseif route~='saved' then return false end
   entry={sector=p[10],binding=binding,buffer=buffer,route=route,dimensions=#pose};tracks[index]=entry
  end
  staged=nil;preflight_ready=false;preflight_attempted=false
  pending={identity={p[5],p[6],p[7],p[8],p[9],p[10],p[11]},index=index,sequence=seq,sector=p[10],binding=entry.binding,
   buffer=entry.buffer,entry=entry,route=entry.route,arrival=arrival,source_time=t,position=pose,rate=rate}
  deadline=last+c.timeout;state='pending'
  local ok,v=pcall(entry.binding.begin,entry.binding,{epoch=c.epoch,generation=c.generation,index=index,sequence=seq,sector_macro=p[10]},arrival)
  return ok and v==true and state=='pending' and check()
 end
 local function accept_operation(raw,kind)
  local p=split(raw)
  if not apply or apply_used or not bound or #p~=10 or p[1]~='M' or p[2]~=c.lease or p[3]~=c.attempt or p[4]~=kind or
   (kind=='APPLY' and apply.observe_limit~=nil) or (kind=='OBSERVE' and (not apply.observe_limit or observe_count>=apply.observe_limit)) or
   ((kind=='APPLY' or kind=='OBSERVE') and not preflight_ready) or (kind=='PREFLIGHT' and preflight_attempted) or
   operation_count>=100000 or operation_requests[p[5]] or
   not token(p[5],32) or p[6]~=c.epoch or p[7]~=c.generation or p[8]~=bound.index_text or
   p[9]~=bound.sequence_text or p[10]~=bound.digest then return false end
  operation_requests[p[5]]=true;operation_count=operation_count+1
  if kind=='PREFLIGHT' then preflight_attempted=true end
  if kind=='APPLY' then apply_used=true;preflight_ready=false end
  if kind=='OBSERVE' then observe_count=observe_count+1;preflight_ready=false end
  operation_identity={p[5],p[6],p[7],p[8],p[9],p[10]};deadline=last+c.timeout
  local active=kind=='PREFLIGHT' and 'preflighting' or 'applying';state=active
  writer=apply.factory({enabled=true,readonly=kind=='PREFLIGHT' and true or nil,
   immediate_readback=kind~='PREFLIGHT' and apply.immediate_readback or nil,
   observe_immediate_only=kind=='OBSERVE' and true or nil,timeout=c.timeout,guard=function()
   return state==active and check() and state==active and last>=bound.arrival and last-bound.arrival<=c.max_age
  end,fault=function(reason)
   local allowed={begin_guard=true,dispatch_guard=true,dispatch_issue=true,pre_guard=true,pre_response=true,pre_inspect=true,
    pre_game=true,pre_distance=true,preflight_log=true,pre_intent=true,pre_write_marker=true,write=true,post_guard=true,post_response=true,
    immediate_inspect=true,immediate_game=true,immediate_log=true,post_inspect=true,post_game=true,post_observation=true,post_readback=true,post_log=true,tick_guard=true,post_dispatch=true,identity=true,begin=true,event=true,tick=true}
   fail((kind=='PREFLIGHT' and 'preflight_' or 'apply_')..(allowed[reason] and reason or 'unknown'))
  end})
  if state~=active or not writer or not check() then return false end
  local input={request=p[5],epoch=c.epoch,generation=c.generation,index=bound.index,sequence=bound.sequence,digest=bound.digest,
   sector_macro=bound.sector,actor_key=bound.actor_key,sector_key=bound.sector_key,zone_key=bound.zone_key,
   target={x=bound.position[1],y=bound.position[2],z=bound.position[3]}}
  return writer:begin(input)==true and state==active and check()
 end
 function api:tick()
  -- The enclosing update owner must keep ticking while paused. A late
  -- packet is a fault; stopped owners never revive or inspect an actor.
  if state=='stopped' and not busy then
   busy=true;local ok,value=pcall(c.net.receive,c.net);busy=false
   if not ok or state~='stopped' or value~=nil then return fail('late_packet')end
   return true
  end
  if busy or (state~='ready' and state~='pending' and state~='applying' and state~='preflighting') then return fail('tick')end
  busy=true;local ok=pcall(function()
   assert(check())
   if state=='pending' then assert(pending.binding:tick() and check())end
   if state=='applying' or state=='preflighting' then
    local active=state;assert(writer:tick() and state==active and check())
    local result=writer:state()
    if active=='applying' and result=='done' then
     assert(not apply.observe_limit)
     assert(c.net:receive()==nil and check());assert(send(reply('APPLIED',operation_identity)))
     state='ready';deadline=nil
    elseif active=='applying' and result=='observed' then
     assert(apply.observe_limit and c.net:receive()==nil and check());assert(send(reply('OBSERVED',operation_identity)))
     state='ready';deadline=nil
    elseif active=='preflighting' and (result=='near' or result=='ready') then
     assert(c.net:receive()==nil and check())
     local identity={};for i,v in ipairs(operation_identity)do identity[i]=v end;identity[#identity+1]=result=='near' and 'NEAR' or 'READY'
     assert(send(reply('PREFLIGHTED',identity)));preflight_ready=result=='ready';state='ready';deadline=nil
    end
   end
   local packet=c.net:receive()
   if packet~=nil then
    assert(state=='ready' and type(packet)=='string' and #packet<=768)
    local p=split(packet)
    if p[4]=='STOP' then
     assert(c.stop and #p==7 and p[1]=='M' and p[2]==c.lease and p[3]==c.attempt and
      token(p[5],32) and p[6]==c.epoch and p[7]==c.generation and check())
     state='stopping';deadline=last+c.timeout
     assert(stop_playback())
     for _,entry in pairs(tracks)do
      assert(type(entry.binding.close)=='function' and entry.binding:close()==true and state=='stopping' and check())
     end
     local ok,closed=pcall(c.stop)
     assert(ok and closed==true and state=='stopping' and check() and c.net:receive()==nil)
     assert(send(reply('STOPPED',{p[5],p[6],p[7]})))
     tracks={};state='stopped';deadline=nil
    elseif p[4]=='APPLY' or p[4]=='OBSERVE' or p[4]=='PREFLIGHT' then assert(accept_operation(packet,p[4])) else assert(not apply_used and accept(packet))end
   end
   if playback then
    for _,entry in pairs(tracks)do
     if entry.playback then assert(entry.playback:tick()==true and check())end
    end
   end
  end);busy=false;if not ok then return fail('tick')end;return true
 end
 function api:apply_event(value)
  if busy or (state~='applying' and state~='preflighting') or not writer then return fail('apply_event')end
  local active=state;busy=true;local ok=pcall(function()assert(check() and writer:event(value)==true and state==active and check())end)
  busy=false;if not ok then return fail('apply_event')end;return true
 end
 function api:event(value,route)
  route=route or 'replica'
  if busy or state~='pending' or delivered or not pending or route~=pending.route then return fail('event')end
  busy=true;local ok=pcall(function()
   assert(check());local accepted=pending.binding:event(value)
   assert(accepted==true and delivered==true and state=='pending' and check())
   local pose={};for i=1,#pending.position do pose[i]=pending.position[i] end
   local rate
   if pending.rate then rate={};for i=1,#pending.rate do rate[i]=pending.rate[i] end end
   local snapshot={frame=pending.sector,sequence=pending.sequence,source_time=pending.source_time,pose=pose,rate=rate}
   local function vector_unchanged(v,expected)
    if type(v)~='table' or getmetatable(v)~=nil or #v~=#expected then return false end
    for k in pairs(v)do if type(k)~='number' or k%1~=0 or k<1 or k>#expected then return false end end
    for i=1,#expected do if v[i]~=expected[i] then return false end end
    return true
   end
   local function snapshot_unchanged()
    if getmetatable(snapshot)~=nil or snapshot.frame~=pending.sector or snapshot.sequence~=pending.sequence or
       snapshot.source_time~=pending.source_time or snapshot.pose~=pose or snapshot.rate~=rate or
       not vector_unchanged(pose,pending.position) then return false end
    for k in pairs(snapshot)do if k~='frame' and k~='sequence' and k~='source_time' and k~='pose' and k~='rate' then return false end end
    return not rate or vector_unchanged(rate,pending.rate)
   end
   local receiver=pending.buffer
   if playback then
    assert(staged and staged.index==pending.index and staged.sequence==pending.sequence)
    local entry=pending.entry
    local identity={actor_key=staged.actor_key,sector_key=staged.sector_key,zone_key=staged.zone_key,
     index=pending.index,epoch=c.epoch,sector_macro=pending.sector}
    if entry.playback then
     for key,value in pairs(identity)do assert(entry.playback_binding[key]==value)end
    else
     entry.playback_binding=identity
     entry.playback=assert(playback.factory({enabled=true,binding=identity,buffer=c.buffer,
      max_age=c.max_age,clock=c.clock,guard=function()return state~='failed' and state~='stopped' and check()end,
      fault=function(reason,uncertain,stage,native_stage)
       fail('playback',playback_diagnostic(stage,native_stage))
      end}))
     assert(type(entry.playback.push)=='function' and type(entry.playback.tick)=='function' and
      type(entry.playback.stop)=='function' and check())
    end
    receiver=entry.playback
   end
   local pushed,reason=receiver:push(snapshot,pending.arrival)
   -- Opt-in playback BOUND means correlated binding and consumed packet, not
   -- applied movement. Paused/expired samples are acknowledged but not buffered.
   if playback and pushed~=true and (reason=='paused' or reason=='expired') then pushed=true end
   assert(pushed==true and state=='pending' and check() and snapshot_unchanged())
   if c.audit then
    local good,accepted=pcall(c.audit,pending.index,pending.sequence,pending.sector,pending.source_time)
    assert(good and accepted==true and state=='pending' and check() and snapshot_unchanged())
   end
   assert(c.net:receive()==nil and check() and snapshot_unchanged())
   if apply and pending.route=='saved' then
    assert(staged and staged.index==pending.index and staged.sequence==pending.sequence)
    if apply.observe_limit then
     if stream_binding then assert(staged.actor_key==stream_binding.actor_key and staged.sector_key==stream_binding.sector_key and staged.zone_key==stream_binding.zone_key)
     else stream_binding={actor_key=staged.actor_key,sector_key=staged.sector_key,zone_key=staged.zone_key} end
    end
    bound={actor_key=staged.actor_key,sector_key=staged.sector_key,zone_key=staged.zone_key,index=pending.index,
     index_text=pending.identity[4],sequence=pending.sequence,sequence_text=pending.identity[5],sector=pending.sector,
     digest=pending.identity[7],arrival=pending.arrival,position={pending.position[1],pending.position[2],pending.position[3]}}
   end
   assert(send(reply('BOUND',pending.identity)));pending=nil;staged=nil;deadline=nil;delivered=nil;state='ready'
  end);busy=false;if not ok then return fail('event')end;return true
 end
 function api:outcome_uncertain()
  if playback_uncertain then return true end
  for _,entry in pairs(tracks)do
   if entry.playback and entry.playback:outcome_uncertain() then return true end
  end
  return false
 end
 function api:state()return state end
 return api
end
function M.new_x4(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(type(o.binding)=='table' and type(o.binding.new_x4)=='function' and type(RegisterEvent)=='function' and type(GetCurRealTime)=='function')
 local c={};for k,v in pairs(o)do c[k]=v end
 local configured_apply_fixture
 if c.saved_apply~=nil then
  assert(type(c.saved_apply)=='table')
  configured_apply_fixture=c.saved_apply.fixture
  assert(configured_apply_fixture==nil or (configured_apply_fixture=='recovery_enh_870' and c.epoch=='4ba7be438ebb04ec5bb85fdb95b5a488'))
 end
 local router=c.event_router
 if router~=nil then
  assert(type(router)=='table' and type(router.issue)=='function' and type(router.owns)=='function' and token(c.router_generation,32) and
   type(c.stop)=='function')
  if c.saved_apply~=nil then
   assert(type(router.supports_saved_apply)=='function' and router:supports_saved_apply()==true)
  end
  assert(not registered and (external_router==nil or external_router==router),'motion event router already reserved')
  external_router=router
 else
  assert(not registered and external_router==nil,'motion event router already reserved');registered=true
 end
 local register=RegisterEvent;local native=c.binding.new_x4;c.clock=GetCurRealTime
 local owner,issue,owns,supports_apply
 if router then
  issue,owns,supports_apply=router.issue,router.owns,router.supports_saved_apply
  local external=c.guard;assert(type(external)=='function')
  c.guard=function()
   return owner~=nil and router.issue==issue and router.owns==owns and router.supports_saved_apply==supports_apply and owns(router,c.router_generation,c.nonce,c.epoch,owner)==true and
    external()==true and router.issue==issue and router.owns==owns and router.supports_saved_apply==supports_apply and owns(router,c.router_generation,c.nonce,c.epoch,owner)==true
  end
  c.register=function()return true end
 else c.register=function(fn)return register('X4AuthorityReplicaMotionBind.Result',fn)~=false end end
 c.factory=function(opt)
  opt.enabled=true;opt.expected_save_path=c.expected_save_path;opt.guard=c.guard;opt.resolve=c.resolve
  if router then opt.md_issue=function(screen,op,args)return issue(router,screen,op,args)end end
  return native(opt)
 end
 if c.saved_baseline~=nil then
  local s=c.saved_baseline
  assert(type(s)=='table' and s.enabled==true and integer(s.baseline) and type(s.guard)=='function' and
   type(s.binding)=='table' and type(s.binding.new_x4)=='function','invalid saved baseline route')
  local baseline,baseline_guard,saved_native=s.baseline,s.guard,s.binding.new_x4
  c.saved_baseline={enabled=true,baseline=baseline,guard=baseline_guard,
   register=router and function()return true end or function(fn)return register('X4AuthoritySavedBaselineMotionBind.Result',fn)~=false end,
   factory=function(opt)
    opt.enabled=true;opt.baseline=baseline;opt.saved_baseline_guard=baseline_guard
    opt.expected_save_path=c.expected_save_path;opt.guard=c.guard;opt.resolve=c.resolve;opt.replica=c.binding
    if router then opt.md_issue=function(screen,op,args)return issue(router,screen,op,args)end end
    return saved_native(opt)
   end}
 end
 if c.saved_apply~=nil then
  local a=c.saved_apply
  assert(type(a)=='table' and a.fixture==configured_apply_fixture and a.enabled==true and type(a.module)=='table' and type(a.module.new_x4)=='function' and
   (a.immediate_readback==nil or a.immediate_readback==true) and
   (a.observe_limit==nil or (integer(a.observe_limit) and a.observe_limit>=2 and a.observe_limit<=8 and a.immediate_readback==true)))
  local native_apply=a.module.new_x4;local apply_log=a.log;local apply_fixture=configured_apply_fixture
  c.saved_apply={enabled=true,immediate_readback=a.immediate_readback,observe_limit=a.observe_limit,register=router and function()return true end or function(fn)return register('X4AuthoritySavedMotionApply.Result',fn)~=false end,
   factory=function(opt)
    opt.expected_save_path=c.expected_save_path;opt.test_profile='45841';opt.resolve=c.resolve;opt.log=apply_log;opt.fixture=apply_fixture
    if router then
     opt.request_nonce=c.nonce
     opt.md_issue=function(screen,op,args)return issue(router,screen,op,args)end
    end
    return native_apply(opt)
   end}
 end
 if c.saved_playback~=nil then
  local settings=c.saved_playback
  assert(c.saved_apply==nil and type(settings)=='table' and settings.enabled==true and
   type(settings.module)=='table' and type(settings.module.new_playback_x4)=='function' and
   type(settings.playback)=='table' and type(settings.record)=='function')
  local native_playback=settings.module.new_playback_x4
  c.saved_playback={enabled=true,factory=function(opt)
   opt.expected_save_path=c.expected_save_path;opt.test_profile='45841';opt.resolve=c.resolve
   opt.fixture=settings.fixture;opt.playback=settings.playback;opt.max_step=settings.max_step
   opt.buffer_options=settings.buffer_options;opt.record=settings.record
   return native_playback(opt)
  end}
 end
 owner=M.new(c);return owner
end
X4LAN_MOTION_CLIENT_OWNER=M
return M
