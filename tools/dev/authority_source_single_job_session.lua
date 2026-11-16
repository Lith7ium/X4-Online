-- Opt-in one-source diagnostic. The existing load owner alone owns onUpdate.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_source_single_job_session~=true then return end
local ffi=require('ffi');ffi.cdef[[bool IsPlayerValid(void);double GetCurrentGameTime(void);]]
local C=ffi.C
local failed=false;local resume_used=false;local source,control,control_net,next_hello,previous=nil,nil,nil,0,nil
local function fail()if not failed then failed=true;DebugError('[X4LAN] AUTH_SOURCE_SINGLE ERROR')end end
local function mark(state)
 local g=tonumber(C.GetCurrentGameTime());assert(g and g==g and g>=0 and g<math.huge)
 DebugError('[X4LAN] AUTH_SOURCE_SINGLE STATE '..state..' '..string.format('%.17g',g))
end
function X4LAN_SOURCE_SINGLE_JOB_TICK()
 if failed then return end
 local ok=pcall(function()
  assert(C.IsPlayerValid())
  if not source then
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
    external_guard=function()return not failed end,fault=fail}
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
  assert(control:on_update())
  if source:state()~='done' then assert(source:tick()) end
  local current=source:state()
  if current~=previous then previous=current;mark(current) end
 end)
 if not ok then fail() end
end
