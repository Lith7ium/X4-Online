-- Opt-in one-source diagnostic. The existing load owner alone owns onUpdate.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_source_single_job_session~=true then return end
local ffi=require('ffi');ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);double GetCurrentGameTime(void);]]
local C=ffi.C
local failed=false;local resume_used=false;local source,control,control_net,next_hello,previous=nil,nil,nil,0,nil
local motion,sampler,source_descriptor;local pending_confirmed,confirmed={},{}
-- Optional caller-supplied baseline fence and candidates; never infer a shared
-- checkpoint from a local marker. Actor references remain in this process.
local saved,bootstrap,staged;local saved_bindings={}
local session_busy,router_busy=false,false
local stage='initial'
local components={job=true,motion_ipc=true,sampler=true,router=true,session=true}
local stages={initial=true,control_update=true,job_tick=true,motion_tick=true,sampler_register=true,
 motion_request=true,sampler_tick=true,motion_empty=true}
local reasons={unknown=true,assertion=true,event=true,start=true,start_state=true,tick=true,tick_state=true,
 descriptor=true,unexpected_descriptor=true,unexpected_source_ack=true,unexpected_source_entry=true,
 unexpected_window_done=true,packet=true,complete=true,register=true,sample=true,close=true}
for _,v in ipairs({'guard','host_ack','host_tick','ipc_tick','ipc_packet','confirmed','final_guard'})do reasons['tick_'..v]=true end
for _,kind in ipairs({'ipc_tick','ipc_packet'})do
 for _,v in ipairs({'candidate_send','deadline_or_guard','foreign_packet','foreign_receipt','gate_ack','gate_begin',
  'gate_create','gate_release','gate_source_ack','gate_state','gate_tick','invalid_candidate','invalid_members',
  'invalid_packet','invalid_source_ack','partial_send','ready_send','rearm_send','source_ack_send',
  'unexpected_candidate','unexpected_packet','unexpected_tick'})do reasons['tick_'..kind..'_'..v]=true end
end
for _,kind in ipairs({'register','tick','sample'})do
 for _,v in ipairs({'actor_key','id_convert','id_roundtrip','dock_values','external_binding'})do reasons[kind..'_'..v]=true end
end
local function allowed(set,value)return type(value)=='string' and set[value] and value or 'unknown' end
local function fail(component,reason)
 if not failed then
  failed=true
  DebugError('[X4LAN] AUTH_SOURCE_SINGLE ERROR '..allowed(components,component)..' '..allowed(reasons,reason)..' '..allowed(stages,stage))
 end
end
local function fault(component)return function(reason)fail(component,reason)end end
local function mark(state)
 local g=tonumber(C.GetCurrentGameTime());assert(g and g==g and g>=0 and g<math.huge)
 DebugError('[X4LAN] AUTH_SOURCE_SINGLE STATE '..state..' '..string.format('%.17g',g))
end
local function source_idle()
 return cfg.authority_source_saved_enabled~=true or not resume_used or
  (source~=nil and source:state()=='observing')
end
function X4LAN_SOURCE_SINGLE_JOB_TICK()
 if failed then return end
 if saved and (session_busy or router_busy) then fail('session','event');return end
 session_busy=true
 local ok=pcall(function()
  assert(C.IsPlayerValid())
  if not source then
   if cfg.authority_source_saved_enabled==true or cfg.authority_source_saved_baseline~=nil then
    assert(not (cfg.authority_source_saved_enabled==true and cfg.authority_source_saved_baseline~=nil))
    local s=cfg.authority_source_saved_baseline
    if cfg.authority_source_saved_enabled==true then
     local epoch,baseline=cfg.authority_source_epoch,cfg.authority_source_baseline
     s={enabled=true,via_ipc=true,nonce=cfg.authority_source_saved_nonce,guard=function(e,b)
      return not failed and source_idle() and e==epoch and b==baseline and not C.IsGamePaused() and
       type(X4LAN_AUTHORITY_MARKER_READY)=='function' and X4LAN_AUTHORITY_MARKER_READY()==true and not failed and source_idle() and not C.IsGamePaused()
     end}
    end
    assert(cfg.authority_source_motion_enabled==true and type(s)=='table' and s.enabled==true and
     type(s.guard)=='function' and ((s.via_ipc==true and s.next_index==nil) or
     (s.via_ipc==nil and type(s.next_index)=='function')) and type(s.nonce)=='string' and
     #s.nonce==32 and s.nonce:match('^[0-9a-f]+$') and
     s.nonce:sub(1,16)~=cfg.authority_source_descriptor_request:sub(1,16) and
     s.nonce:sub(1,16)~=cfg.authority_source_motion_nonce:sub(1,16))
    saved={guard=s.guard,next_index=s.next_index,nonce=s.nonce,via_ipc=s.via_ipc==true,
     epoch=cfg.authority_source_epoch,baseline=cfg.authority_source_baseline}
   end
   local engine=assert(X4LAN_AUTHORITY_X4_CONTROL_ENGINE.new({enabled=true,test_profile='45841'}))
   local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
   control_net=assert(lib.open('127.0.0.1',cfg.authority_source_control_port))
   local source_net=assert(lib.open('127.0.0.1',cfg.authority_source_job_port))
   control=assert(X4LAN_AUTHORITY_CONTROL_STATE.new({enabled=true,owner='isolated-source',
    world_epoch=cfg.authority_ticket.world_epoch,timeout_seconds=cfg.authority_source_host_timeout},engine,function(row)
     assert(control_net:send('RECEIPT|'..cfg.authority_source_control_lease..'|'..cfg.authority_ticket.world_epoch..'|'..
      string.format('%.0f',row.request_id)..'|'..row.operation..'|'..row.status))
    end))
   local owner_cfg={enabled=true,
    sequence=1,index=cfg.authority_source_baseline+1,max_events=cfg.authority_source_max_events,
    continuous=cfg.authority_source_continuous,
    lease=cfg.authority_source_lease,attempt=cfg.authority_source_attempt,epoch=cfg.authority_source_epoch,
    generation=cfg.authority_source_generation,descriptor_request=cfg.authority_source_descriptor_request,
    capacity=cfg.authority_source_capacity,
    timeout=cfg.authority_source_timeout,host_timeout=cfg.authority_source_host_timeout,window=cfg.authority_source_window,
    expected_save_path=cfg.authority_load_save_path,net=source_net,
    host=X4LAN_AUTHORITY_JOB_REGISTRY_HOST,probe=X4LAN_AUTHORITY_JOB_REGISTRY_PROBE,
    descriptor=X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE,resolve=X4LAN_RESOLVE_STRING,
    ipc=X4LAN_AUTHORITY_SOURCE_JOB_IPC,gate=X4LAN_AUTHORITY_JOB_DELIVERY,
    external_guard=function()return not failed end,fault=fault('job'),diagnostics=cfg.authority_source_motion_enabled==true}
   if cfg.authority_source_motion_enabled==true then
    local motion_net=assert(lib.open('127.0.0.1',cfg.authority_source_motion_port))
    motion=assert(X4LAN_AUTHORITY_SOURCE_MOTION_IPC.new({enabled=true,lease=cfg.authority_source_motion_lease,
     attempt=cfg.authority_source_motion_attempt,epoch=cfg.authority_source_epoch,generation=cfg.authority_source_generation,
     timeout=cfg.authority_source_host_timeout,clock=GetCurRealTime,guard=function()return not failed and source_idle() end,net=motion_net,
     saved_baseline=saved and saved.via_ipc and {limit=saved.baseline,guard=function(epoch,baseline)
      return not failed and not C.IsGamePaused() and saved.guard(epoch,baseline)==true and not failed and not C.IsGamePaused()
     end} or nil,fault=fault('motion_ipc')}))
    sampler=assert(X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER.new_x4({enabled=true,epoch=cfg.authority_source_epoch,
     generation=cfg.authority_source_generation,nonce=cfg.authority_source_motion_nonce,max_tracks=100000,scan_budget=64,
     interval=.1,timeout=cfg.authority_source_host_timeout,min_dt=.02,max_dt=1,
     diagnostics=true,
     descriptor=X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE,resolve=X4LAN_RESOLVE_STRING,
     expected_save_path=cfg.authority_load_save_path,guard=function()return not failed and source_idle() and not C.IsGamePaused() end,
     binding_guard=function(row,actor)
      local known=confirmed[row.index]
      return known~=nil and known.sequence==row.sequence and known.actor==actor
     end,
     saved_baseline_limit=saved and saved.baseline or nil,
     saved_baseline_guard=saved and function(row,actor)
      local known=saved_bindings[row.index]
      return not failed and row.epoch==saved.epoch and known~=nil and known.actor==actor and saved.guard(saved.epoch,saved.baseline)==true and not failed
     end or nil,fault=fault('sampler')}))
    if saved then
     bootstrap=assert(X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP.new_x4({enabled=true,
      epoch=saved.epoch,baseline=saved.baseline,nonce=saved.nonce,
      timeout=cfg.authority_source_host_timeout,expected_save_path=cfg.authority_load_save_path,
      resolve=X4LAN_RESOLVE_STRING,guard=function()return not failed and source_idle() end,baseline_guard=saved.guard,
      complete=function(index,actor,sector)
       if failed or staged or saved_bindings[index] then return false end
       staged={index=index,actor=actor,sector=sector};return true
      end}))
    end
    owner_cfg.on_confirmed=function(row,actor)
     if failed or #pending_confirmed>=1024 or confirmed[row.index] then return false end
     confirmed[row.index]={sequence=row.sequence,actor=actor}
     pending_confirmed[#pending_confirmed+1]={row=row,actor=actor};return true
    end
    owner_cfg.descriptor_router=function(callback)
     if source_descriptor then return false end;source_descriptor=callback;return true
    end
    assert(RegisterEvent('X4AuthorityJobDescriptorProbe.Result',function(_,value)
     if failed then return end
     if saved and (session_busy or router_busy) then fail('router','event');return end
     router_busy=true
     local ok=pcall(function()
      assert(type(value)=='string');local id=value:match('^([0-9a-f]+)|')
      if sampler:expected_request()==id and id~=nil then
       assert(motion:requested());local accepted,snapshot=sampler:event(value);assert(accepted)
       assert(motion:complete(snapshot))
      elseif bootstrap and bootstrap:expected_request()==id and id~=nil then
       assert(not staged and bootstrap:event(value)==true and bootstrap:state()=='idle' and not failed)
       local item=assert(staged);staged=nil
       if saved.via_ipc then assert(motion:saved_request()==item.index)end
       assert(not saved_bindings[item.index] and #pending_confirmed<1024 and
        saved.guard(saved.epoch,saved.baseline)==true and not failed)
       saved_bindings[item.index]={actor=item.actor}
       pending_confirmed[#pending_confirmed+1]={row={epoch=saved.epoch,index=item.index,
        classification='saved_baseline'},actor=item.actor}
      elseif source and source:expected_descriptor()==id and id~=nil then
       assert(source_descriptor);source_descriptor(nil,value)
       assert(not failed and source:state()~='failed')
      else error('unexpected descriptor response')end
     end)
     router_busy=false
     if not ok then fail('router','event')end
    end)~=false)
    assert(motion:start())
   end
   source=assert(X4LAN_AUTHORITY_SOURCE_SINGLE_JOB_OWNER.new_x4(owner_cfg))
   assert(source:start());previous=source:state();mark(previous)
  end
  local now=GetCurRealTime()
  if now>=next_hello then
   assert(control_net:send('HELLO|'..cfg.authority_source_control_lease..'|'..cfg.authority_ticket.world_epoch))
   next_hello=now+.25
  end
  for _=1,16 do
   local packet=control_net:receive();if packet==nil then break end
   local lease,epoch,id,op=packet:match('^CMD|([0-9a-f]+)|([0-9a-f]+)|(%d+)|([a-z]+)$')
   assert(lease==cfg.authority_source_control_lease and epoch==cfg.authority_ticket.world_epoch)
   assert(id and #id<=16 and not id:match('^0') and op=='resume' and not resume_used and source:state()=='observing')
   resume_used=true
   assert(control:submit('isolated-source',epoch,tonumber(id),op))
  end
  stage='control_update';assert(control:on_update())
  assert(source_idle())
  if source:state()~='done' then stage='job_tick';assert(source:tick()) end
  assert(source_idle())
  if motion then
   stage='motion_tick';assert(motion:tick())
   if bootstrap and not C.IsGamePaused() then
    assert(bootstrap:tick() and not failed)
    if bootstrap:state()=='idle' and #pending_confirmed==0 then
     local index=saved.via_ipc and motion:saved_request() or (not saved.via_ipc and saved.next_index() or nil)
     assert(not failed)
     if index~=nil then assert(bootstrap:begin(index) and not failed) end
    end
   end
   if sampler:state()=='ready' and #pending_confirmed>0 and not C.IsGamePaused() then
    stage='sampler_register';local item=table.remove(pending_confirmed,1);assert(sampler:register(item.row,item.actor) and not failed)
    if saved and saved.via_ipc and item.row.classification=='saved_baseline' then
     assert(motion:saved_request()==item.row.index and saved.guard(saved.epoch,saved.baseline)==true and not failed)
     assert(motion:saved_registered(item.row.index) and not failed)
    end
   end
   if motion:requested() then
    stage='motion_request'
    assert(not C.IsGamePaused())
    stage='sampler_tick';assert(sampler:tick())
    if sampler:state()=='ready' then stage='motion_empty';assert(motion:complete(nil)) end
   end
  end
  local current=source:state()
  if current~=previous then previous=current;mark(current) end
 end)
 session_busy=false
 if not ok then fail('session','assertion') end
end
