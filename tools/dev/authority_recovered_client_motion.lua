-- Private client motion probe; sustained playback requires an explicit fixture opt-in.
-- The existing participant
-- update owner calls tick; process, FD, checkpoint and STOPPED are external.
local M={}
local player_sector_event_claimed=false
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
-- Only static diagnostic codes may cross into X4's log. Never interpolate a
-- callback's arbitrary text: it may contain wire data or control characters.
local owner_reasons={playback=true,start=true,late_packet=true,tick=true,apply_event=true,event=true}
local playback_stages={}
for word in ('state clock guard paused buffer_reset sample arrival sequence buffer_push read read_pose game_read game_value game_clock readback_record render render_frame observation_record distance write write_state'):gmatch('%S+')do playback_stages[word]=true end
local native_stages={}
for word in ('initial profile profile_recheck references actor sector zone player player_container docking fixture fixture_sector fixture_code validated position_read setter'):gmatch('%S+')do native_stages[word]=true end
local function playback_diagnostic(stage,native_stage)
 return {stage=playback_stages[stage] and stage or 'unknown',native_stage=native_stages[native_stage] and native_stage or 'unknown'}
end
local writer_reasons={begin_guard=true,dispatch_guard=true,dispatch_issue=true,pre_guard=true,pre_response=true,
 pre_inspect=true,pre_game=true,pre_distance=true,preflight_log=true,pre_intent=true,pre_write_marker=true,write=true,
 post_guard=true,post_response=true,immediate_inspect=true,immediate_game=true,immediate_log=true,post_inspect=true,
 post_game=true,post_observation=true,post_readback=true,post_log=true,tick_guard=true,post_dispatch=true,
 identity=true,begin=true,event=true,tick=true,unknown=true}
local router_reasons={guard_reentrant=true,reentrant_or_failed=true,operation=true}
local function safe_fault(source,reason)
 if type(reason)~='string' then return source end
 if source=='router' and router_reasons[reason] then return 'router_'..reason end
 if source=='owner' then
  if owner_reasons[reason] then return 'owner_'..reason end
  local operation,stage=reason:match('^(preflight)_(%a[%a_]*)$')
  if not operation then operation,stage=reason:match('^(apply)_(%a[%a_]*)$') end
  if operation and writer_reasons[stage] then return 'owner_'..operation..'_'..stage end
 end
 return source
end
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 local fixed={};for k,v in pairs(c)do fixed[k]=v end;c=fixed
 for _,name in ipairs({'guard','running','router_factory','owner_factory','fault'})do assert(type(c[name])=='function',name)end
 local failed,busy=false,false;local router,owner,sector_reader
 local sector_phase,sector_staged,bound_ready='disabled',nil,nil
 local function fail(reason,diagnostic)
  local retained=diagnostic and playback_diagnostic(diagnostic.stage,diagnostic.native_stage)
  if not failed then failed=true;pcall(c.fault,reason,retained)end
  return false
 end
 local function context()
  local ok,v=pcall(c.guard);return not failed and ok and v==true
 end
 local function stop_sector_reader()
  if sector_phase=='disabled' then return true end
  if sector_phase~='done' then return false end
  local ok,closed=pcall(sector_reader.close,sector_reader)
  if not ok or closed~=true or sector_reader:state()~='closed' or not context() then return false end
  sector_phase='closed';return true
 end
 router=assert(c.router_factory({guard=context,fault=function(reason)fail(safe_fault('router',reason))end}))
 assert(router:start() and context())
 owner=assert(c.owner_factory({router=router,guard=context,stop=function()
  return context() and c.running()==true and router:state()=='active' and stop_sector_reader()
 end,fault=function(reason,uncertain,diagnostic)fail(safe_fault('owner',reason),diagnostic)end}))
 if c.player_sector==nil then
  assert(router:attach(c.router_generation,c.nonce,c.epoch,owner) and owner:start() and context())
 else
  assert(router:attach(c.router_generation,c.nonce,c.epoch,owner) and context())
  local p=c.player_sector
  assert(type(p)=='table' and token(c.epoch) and token(p.incarnation) and token(p.nonce) and
   c.epoch~=p.incarnation and c.epoch~=p.nonce and p.incarnation~=p.nonce and
   type(p.factory)=='function' and type(p.register)=='function' and type(p.report)=='function' and
   (p.after_bound==nil or (p.after_bound==true and type(p.bound_ready)=='function')))
  local incarnation,nonce,factory,register,report=p.incarnation,p.nonce,p.factory,p.register,p.report
  bound_ready=p.after_bound and p.bound_ready or nil
  sector_phase=bound_ready and 'waiting_bound' or 'idle'
  local function sector_guard(value)
   if value~=incarnation or not context() then return false end
   local ok,running=pcall(c.running)
   local status,phase=pcall(owner.state,owner)
   return ok and running==true and status and phase~='stopped' and context()
  end
  sector_reader=assert(factory({epoch=c.epoch,incarnation=incarnation,nonce=nonce,guard=sector_guard,
   complete=function(result)
    if sector_phase~='pending' or sector_staged~=nil or type(result)~='table' or getmetatable(result)~=nil or
     result.epoch~=c.epoch or result.incarnation~=incarnation or result.sequence~=1 or
     type(result.sector_macro)~='string' or not result.sector_macro:match('^[A-Za-z0-9_]+$') or
     #result.sector_macro>128 then return false end
    for key in pairs(result)do if key~='epoch' and key~='incarnation' and key~='sequence' and key~='sector_macro' then return false end end
    sector_staged={epoch=result.epoch,incarnation=result.incarnation,sequence=result.sequence,sector_macro=result.sector_macro}
    return true
   end}))
  assert(type(sector_reader.begin)=='function' and type(sector_reader.event)=='function' and
   type(sector_reader.tick)=='function' and type(sector_reader.state)=='function' and type(sector_reader.close)=='function')
  assert(register(function(value)
   if busy or failed or sector_phase~='pending' then return fail('sector_event')end
   busy=true
   local ok=pcall(function()
    assert(sector_guard(incarnation) and sector_reader:event(value)==true and
     sector_reader:state()=='idle' and sector_staged and sector_guard(incarnation))
    local staged=sector_staged;local macro=staged.sector_macro
    assert(report(staged)==true and sector_guard(incarnation) and sector_reader:state()=='idle' and
     getmetatable(staged)==nil and staged.epoch==c.epoch and staged.incarnation==incarnation and
     staged.sequence==1 and staged.sector_macro==macro)
    for key in pairs(staged)do assert(key=='epoch' or key=='incarnation' or key=='sequence' or key=='sector_macro')end
    sector_staged=nil;sector_phase='done'
   end)
   busy=false;if not ok then return fail('sector_event')end;return true
  end)==true and context())
  assert(owner:start() and context())
 end
 local api={}
 function api:tick()
  if busy or failed then return fail('state')end
  busy=true
  local ok=pcall(function()
   assert(context() and router:state()=='active')
   local phase=owner:state()
   assert(phase=='stopped' or c.running()==true)
   assert(owner:tick()==true and context() and router:state()=='active')
   if sector_reader then
    if sector_phase=='waiting_bound' then
     local checked,ready=pcall(bound_ready)
     assert(checked and type(ready)=='boolean' and context())
     if ready then sector_phase='idle' end
    end
    if sector_phase=='idle' then
     assert(owner:state()~='stopped' and c.running()==true)
     sector_phase='pending';assert(sector_reader:begin()==true)
    elseif sector_phase=='pending' then assert(sector_reader:tick()==true)
    else assert(sector_phase=='waiting_bound' or sector_phase=='done' or sector_phase=='closed')end
   end
  end)
  busy=false;if not ok then return fail('tick')end
  if c.after_stopped then
   local checked,phase=pcall(owner.state,owner)
   if checked and phase=='stopped' then pcall(c.after_stopped) end
  end
  return true
 end
 function api:state()return failed and 'failed' or owner:state()end
 return api
end
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 local fixed={};for k,v in pairs(c)do fixed[k]=v end;c=fixed
 local function integer(v)return type(v)=='number' and v==v and v%1==0 end
 assert(type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save' and
  integer(c.port) and c.port>=1 and c.port<=65535 and integer(c.baseline) and c.baseline>=1 and c.baseline<=200000 and
  type(c.timeout)=='number' and c.timeout==c.timeout and c.timeout>0 and c.timeout<=30)
 local allowed={};local locked
 if c.indices==nil then
  assert(integer(c.index) and c.index>=1 and c.index<=c.baseline)
  locked=string.format('%.0f',c.index);allowed[locked]=true
 else
  assert(c.index==nil and type(c.indices)=='table' and getmetatable(c.indices)==nil and #c.indices>=1 and #c.indices<=32)
  local count=0
  for k in pairs(c.indices)do assert(integer(k) and k>=1 and k<=#c.indices);count=count+1 end
  assert(count==#c.indices)
  for i=1,count do
   local n=c.indices[i];assert(integer(n) and n>=1 and n<=c.baseline)
   local key=string.format('%.0f',n);assert(not allowed[key]);allowed[key]=true
  end
 end
 local saved_playback_fixture=c.saved_playback_fixture
 assert(saved_playback_fixture==nil or (saved_playback_fixture=='recovery_enh_870' and
  c.saved_apply_fixture==nil and c.epoch=='4ba7be438ebb04ec5bb85fdb95b5a488' and c.index==1318 and c.indices==nil))
 if saved_playback_fixture then
  assert(type(X4LAN_MOTION_PLAYBACK)=='table' and type(X4LAN_MOTION_PLAYBACK.new)=='function' and
   type(X4LAN_SAVED_MOTION_APPLY)=='table' and type(X4LAN_SAVED_MOTION_APPLY.new_playback_x4)=='function')
 end
 local saved_apply_fixture=c.saved_apply_fixture
 assert(saved_apply_fixture==nil or (saved_apply_fixture=='recovery_enh_870' and
  c.epoch=='4ba7be438ebb04ec5bb85fdb95b5a488' and c.index==1318 and c.indices==nil))
 if saved_apply_fixture then
  assert(type(X4LAN_SAVED_MOTION_APPLY)=='table' and type(X4LAN_SAVED_MOTION_APPLY.new_x4)=='function')
 end
 local seen={}
 for _,key in ipairs({'lease','attempt','epoch','generation','nonce','router_generation'})do
  local v=c[key];assert(token(v) and not seen[v]);seen[v]=true
 end
 local sector_config
 if c.player_sector~=nil then
  local p=c.player_sector
  assert(type(p)=='table' and getmetatable(p)==nil and token(p.incarnation) and token(p.nonce))
  for key in pairs(p)do assert(key=='incarnation' or key=='nonce' or key=='after_bound')end
  assert(p.after_bound==nil or p.after_bound==true)
  assert(p.incarnation~=p.nonce and not seen[p.incarnation] and not seen[p.nonce])
  sector_config={incarnation=p.incarnation,nonce=p.nonce,after_bound=p.after_bound}
  assert(type(X4LAN_PLAYER_SECTOR_INTEREST)=='table' and type(X4LAN_PLAYER_SECTOR_INTEREST.new_x4)=='function')
 end
 local ffi=require('ffi');ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local netlib=X4LAN_LOCAL_UDP_MODULE.load(ffi.os,package.loadlib)
 local net=assert(netlib.open('127.0.0.1',c.port))
 assert(type(net.pending)=='function')
 local function environment()
  local p=C.GetSaveFolderPath()
  return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==c.expected_save_path and
   C.IsPlayerValid() and type(X4LAN_RECOVERED_CLIENT_LOAD_READY)=='function' and X4LAN_RECOVERED_CLIENT_LOAD_READY()==true
 end
 -- At most one permitted saved ship is in scope. With a candidate list the
 -- first correlated BIND seals the index; an invalid attempt faults the owner.
 -- Saved apply is one-shot; playback explicitly permits newer XYZ BIND samples.
 -- Existing ordinary binding behavior is unchanged.
 local bound_phase=sector_config and sector_config.after_bound and 'waiting_bind' or nil
 local expected_bound
 local apply_phase=saved_apply_fixture and 'waiting_bind' or nil
 local apply_identity,apply_request
 -- Timing is diagnostic only: invalid readings do not change guard logic.
 -- Clock reads add overhead. Logging follows the error message after failure,
 -- or runs after the owner reaches STOPPED, outside its active operation.
 local bound_sent_at,preflight_received_at,timing_reported
 local function timing_clock()
  local ok,value=pcall(GetCurRealTime)
  if not ok or type(value)~='number' or value~=value or value<0 or value>1e12 then return nil end
  return value
 end
 local function report_timing()
  if not saved_apply_fixture or timing_reported then return end
  timing_reported=true
  local message='[X4LAN] AUTH_RECOVERED_CLIENT_MOTION TIMING bound_to_preflight_lower_bound_seconds='
  if bound_sent_at and preflight_received_at and preflight_received_at>=bound_sent_at then
   -- Round down: this remains a lower bound on the age checked by the owner.
   message=message..('%.3f'):format(math.floor((preflight_received_at-bound_sent_at)*1000)/1000)
  else message=message..'unavailable' end
  pcall(DebugError,message)
 end
 -- Playback evidence is portable, fixed-schema and bounded to 66 records:
 -- one guarded initial read, at most 64 summaries at <=1 Hz, one STOPPED.
 -- BOUND remains binding/consumption only. The first BIND is never played.
 local playback_sequence,playback_source_time,playback_expected_reply=nil,nil,nil
 local playback_samples,playback_observations,playback_readbacks,playback_reports=0,0,0,0
 local playback_controller,playback_latest,playback_next_report=nil,nil,nil
 local playback_stopped_reported=false
 local playback_drained=false
 local playback_sector='cluster_06_sector001_macro'
 local playback_phases={waiting=true,held=true,interpolated=true,extrapolated=true,frozen=true,['held-no-rate']=true}
 local function finite(value)
  return type(value)=='number' and value==value and math.abs(value)<math.huge
 end
 local function playback_log(kind,uncertain)
  assert(playback_latest and (kind=='SUMMARY' or kind=='STOPPED'))
  local value=playback_latest
  local line=('[X4LAN] AUTH_CLIENT_PLAYBACK %s version=1 epoch=%s index=1318 sector=%s report=%d samples=%d observations=%d readbacks=%d source_sequence=%.0f phase=%s local_time=%.17g game_time=%.17g actual_x=%.17g actual_y=%.17g actual_z=%.17g target_x=%.17g target_y=%.17g target_z=%.17g error=%.17g'):format(
   kind,c.epoch,playback_sector,playback_reports,playback_samples,playback_observations,playback_readbacks,
   value.sequence,value.phase,value.local_time,value.game_time,value.actual.x,value.actual.y,value.actual.z,
   value.target.x,value.target.y,value.target.z,value.error)
  if kind=='STOPPED' then line=line..' uncertain='..(uncertain and '1' or '0')..' drained='..(playback_drained and '1' or '0') end
  DebugError(line)
 end
 local function playback_record(event)
  assert(type(event)=='table' and event.index==1318 and event.epoch==c.epoch and event.sector_macro==playback_sector)
  assert(event.kind=='observation' or event.kind=='readback')
  for _,pose in ipairs({event.actual,event.target}) do
   assert(type(pose)=='table')
   for _,axis in ipairs({'x','y','z'})do assert(finite(pose[axis]))end
  end
  assert(finite(event.local_time) and finite(event.game_time) and integer(event.source_sequence) and event.source_sequence>=1)
  local phase=playback_latest.phase
  if event.kind=='observation' then
   assert(playback_phases[event.phase]);phase=event.phase;playback_observations=playback_observations+1
  else playback_readbacks=playback_readbacks+1 end
  local dx,dy,dz=event.actual.x-event.target.x,event.actual.y-event.target.y,event.actual.z-event.target.z
  playback_latest={actual={x=event.actual.x,y=event.actual.y,z=event.actual.z},
   target={x=event.target.x,y=event.target.y,z=event.target.z},sequence=event.source_sequence,phase=phase,
   local_time=event.local_time,game_time=event.game_time,error=math.sqrt(dx*dx+dy*dy+dz*dz)}
  if playback_reports<64 and event.local_time>=playback_next_report then
   playback_reports=playback_reports+1;playback_next_report=event.local_time+1;playback_log('SUMMARY')
  end
  return true
 end
 local playback_adapter={new=function(options)
  assert(saved_playback_fixture and not playback_controller and not C.IsGamePaused() and options.guard()==true)
  local actual=options.read()
  assert(not C.IsGamePaused() and options.guard()==true and type(actual)=='table')
  for _,axis in ipairs({'x','y','z'})do assert(finite(actual[axis]))end
  local local_time,game_time=options.clock(),options.game()
  assert(finite(local_time) and local_time>=0 and finite(game_time) and game_time>=0 and
   not C.IsGamePaused() and options.guard()==true)
  DebugError(('[X4LAN] AUTH_CLIENT_PLAYBACK INITIAL version=1 epoch=%s index=1318 sector=%s source_sequence=%.0f local_time=%.17g game_time=%.17g x=%.17g y=%.17g z=%.17g'):format(
   c.epoch,playback_sector,playback_sequence,local_time,game_time,actual.x,actual.y,actual.z))
  assert(not C.IsGamePaused() and options.guard()==true)
  playback_latest={actual={x=actual.x,y=actual.y,z=actual.z},target={x=actual.x,y=actual.y,z=actual.z},
   sequence=playback_sequence,phase='waiting',local_time=local_time,game_time=game_time,error=0}
  playback_next_report=local_time+1
  playback_controller=assert(X4LAN_MOTION_PLAYBACK.new(options))
  local first=true
  return {push=function(_,snapshot,arrival)
    if first then
     assert(snapshot.sequence==playback_sequence and snapshot.frame==playback_sector)
     first=false;return true -- Enrollment only; never buffer its arbitrary target.
    end
    return playback_controller:push(snapshot,arrival)
   end,
   tick=function()return playback_controller:tick()end,
   stop=function()
    playback_drained=playback_controller:state()=='stale' and not playback_controller:outcome_uncertain()
    return playback_controller:stop()
   end,
   state=function()return playback_controller:state()end,
   outcome_uncertain=function()return playback_controller:outcome_uncertain()end}
 end}
 local function playback_stopped()
  if not playback_controller or playback_stopped_reported then return end
  playback_stopped_reported=true
  playback_log('STOPPED',playback_controller:outcome_uncertain())
 end
 local checked_net={send=function(_,value)
  if type(value)=='string' and value:sub(1,2)=='R|' then
   local fields={};for item in (value..'|'):gmatch('(.-)|')do fields[#fields+1]=item end
   if saved_playback_fixture and fields[4]=='BOUND' then
    assert(value==playback_expected_reply);playback_expected_reply=nil
   end
   if fields[4]=='BOUND' and (bound_phase or apply_phase) then
    if bound_phase and (not saved_playback_fixture or bound_phase~='sent') then assert(bound_phase=='waiting_ack' and value==expected_bound) end
    if apply_phase then assert(apply_phase=='binding' and value==apply_identity.bound_reply) end
    local sent=net:send(value)
    if sent==true then
     if bound_phase then bound_phase='sent' end
     if apply_phase then apply_phase='bound';bound_sent_at=timing_clock() end
    end
    return sent
   elseif apply_phase and fields[4]=='PREFLIGHTED' then
    assert(apply_phase=='preflighting' and #fields==11 and fields[5]==apply_request and
     fields[6]==c.epoch and fields[7]==c.generation and fields[8]=='1318' and
     fields[9]==apply_identity.sequence and fields[10]==apply_identity.digest and
     (fields[11]=='READY' or fields[11]=='NEAR'))
    local sent=net:send(value)
    if sent==true then apply_phase=fields[11]=='READY' and 'ready' or 'near' end
    return sent
   elseif apply_phase and fields[4]=='APPLIED' then
    assert(apply_phase=='applying' and #fields==10 and fields[5]==apply_request and
     fields[6]==c.epoch and fields[7]==c.generation and fields[8]=='1318' and
     fields[9]==apply_identity.sequence and fields[10]==apply_identity.digest)
    local sent=net:send(value);if sent==true then apply_phase='applied' end;return sent
   end
  end
  return net:send(value)
 end,receive=function()
  local pending=net:pending();assert(type(pending)=='boolean')
  -- Do not consume an arrival racing with a negative readability check:
  -- invalid datagrams return nil from receive and must remain for next tick.
  if not pending then return nil end
  local value=net:receive()
  assert(value~=nil)
  assert(type(value)=='string' and #value<=768)
  local fields={};for item in (value..'|'):gmatch('(.-)|')do fields[#fields+1]=item end
  assert(fields[1]=='M' and fields[2]==c.lease and fields[3]==c.attempt)
  if fields[4]=='BIND' then
   assert(#fields==18 and token(fields[5]) and fields[6]==c.epoch and fields[7]==c.generation and allowed[fields[8]])
   if saved_playback_fixture then
    assert(fields[8]=='1318' and fields[10]==playback_sector and not playback_expected_reply)
    local sequence,source_time=tonumber(fields[9]),tonumber(fields[12])
    assert(fields[9]:match('^[1-9]%d*$') and #fields[9]<=16 and integer(sequence) and sequence<=9007199254740991 and
     string.format('%.0f',sequence)==fields[9] and (not playback_sequence or sequence>playback_sequence) and
     finite(source_time) and source_time>=0 and source_time<=1e12 and
     (not playback_source_time or source_time>playback_source_time))
    playback_sequence,playback_source_time=sequence,source_time;playback_samples=playback_samples+1
    playback_expected_reply=table.concat({'R',c.lease,c.attempt,'BOUND',unpack(fields,5,11)},'|')
   end
   if saved_apply_fixture then
    assert(apply_phase=='waiting_bind' and fields[10]=='cluster_06_sector001_macro')
    apply_identity={sequence=fields[9],digest=fields[11],
     bound_reply=table.concat({'R',c.lease,c.attempt,'BOUND',unpack(fields,5,11)},'|')}
    apply_phase='binding'
   end
   if locked==nil then locked=fields[8]end
   assert(fields[8]==locked)
   if bound_phase then
    assert(bound_phase=='waiting_bind' or (saved_playback_fixture and bound_phase=='sent'))
    if bound_phase=='waiting_bind' then
    expected_bound=table.concat({'R',c.lease,c.attempt,'BOUND',unpack(fields,5,11)},'|')
    bound_phase='waiting_ack'
    end
   end
  elseif saved_apply_fixture and (fields[4]=='PREFLIGHT' or fields[4]=='APPLY') then
   assert(#fields==10 and token(fields[5]) and fields[6]==c.epoch and fields[7]==c.generation and
    fields[8]=='1318' and apply_identity and fields[9]==apply_identity.sequence and fields[10]==apply_identity.digest)
   if fields[4]=='PREFLIGHT' then
    assert(apply_phase=='bound');preflight_received_at=timing_clock();apply_phase='preflighting'
   else assert(apply_phase=='ready');apply_phase='applying' end
   apply_request=fields[5]
  else assert(fields[4]=='STOP' and #fields==7)end
  return value
 end}
 local player_sector
 if sector_config then
  player_sector={incarnation=sector_config.incarnation,nonce=sector_config.nonce,
   factory=function(o)
    o.enabled=true;o.timeout=c.timeout;o.expected_save_path=c.expected_save_path;o.resolve=X4LAN_RESOLVE_STRING
    return X4LAN_PLAYER_SECTOR_INTEREST.new_x4(o)
   end,
   register=function(callback)
    assert(not player_sector_event_claimed);player_sector_event_claimed=true
    return RegisterEvent('X4AuthorityPlayerSectorInterest.Result',function(_,value)callback(value)end)~=false
   end,
   report=function(result)
    DebugError('[X4LAN] AUTH_CLIENT_SECTOR observed sector='..result.sector_macro)
    return true
   end}
  if sector_config.after_bound then
   player_sector.after_bound=true
   player_sector.bound_ready=function()return bound_phase=='sent'end
  end
 end
 return M.new({enabled=true,epoch=c.epoch,nonce=c.nonce,router_generation=c.router_generation,player_sector=player_sector,
  after_stopped=saved_playback_fixture and playback_stopped or (saved_apply_fixture and report_timing or nil),
  guard=environment,running=function()return not C.IsGamePaused()end,
  router_factory=function(o)
   local options={enabled=true,max_generations=1,max_tracks=1,
    guard=o.guard,retire_guard=function()return false end,fault=o.fault}
   if saved_apply_fixture then
    options.saved_apply=true;options.saved_apply_fixture=saved_apply_fixture;options.max_apply_requests=2
   end
   return X4LAN_CLIENT_MOTION_EVENT_ROUTER.new_x4(options)
  end,
  owner_factory=function(o)
   local options={enabled=true,net=checked_net,lease=c.lease,attempt=c.attempt,
    epoch=c.epoch,generation=c.generation,nonce=c.nonce,router_generation=c.router_generation,event_router=o.router,
    timeout=c.timeout,max_age=saved_playback_fixture and math.min(c.timeout,1) or c.timeout,max_tracks=1,expected_save_path=c.expected_save_path,
    resolve=X4LAN_RESOLVE_STRING,binding=X4LAN_REPLICA_MOTION_BINDING,buffer=X4LAN_MOTION_BUFFER,
    saved_baseline={enabled=true,baseline=c.baseline,binding=X4LAN_SAVED_BASELINE_MOTION_BINDING,
     guard=function(e,n)return environment() and not C.IsGamePaused() and e==c.epoch and n==c.baseline end},
    guard=o.guard,stop=o.stop,fault=o.fault}
   if saved_apply_fixture then
    options.saved_apply={enabled=true,fixture=saved_apply_fixture,module=X4LAN_SAVED_MOTION_APPLY,
     log=function(line)DebugError('[X4LAN] AUTH_RECOVERED_CLIENT_APPLY '..line);return true end}
   end
   if saved_playback_fixture then
    options.saved_playback={enabled=true,fixture=saved_playback_fixture,module=X4LAN_SAVED_MOTION_APPLY,
     playback=playback_adapter,max_step=50,record=playback_record,
     buffer_options={delay=.15,horizon=.35,stale=.75}}
   end
   return X4LAN_MOTION_CLIENT_OWNER.new_x4(options)
  end,
  fault=function(reason,diagnostic)
   local retained=diagnostic and playback_diagnostic(diagnostic.stage,diagnostic.native_stage)
   -- safe_fault produces only the static codes above. Wrapper-owned reasons
   -- are also literals; unexpected values fall back to the original message.
   local wrapper_reasons={state=true,tick=true,sector_event=true}
   local known=wrapper_reasons[reason]
   if type(reason)=='string' and reason:match('^owner_') then
    known=safe_fault('owner',reason:sub(7))==reason
   elseif type(reason)=='string' and reason:match('^router_') then
    known=safe_fault('router',reason:sub(8))==reason
   end
   if playback_controller then playback_controller:stop() end
   local detail=''
   if reason=='owner_playback' then
    retained=retained or playback_diagnostic(nil,nil)
    detail=' stage='..retained.stage..' native_stage='..retained.native_stage
   end
   DebugError('[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR'..(known and ' reason='..reason or '')..detail)
   report_timing()
  end})
end
X4LAN_RECOVERED_CLIENT_MOTION=M
return M
