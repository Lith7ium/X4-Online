-- Opt-in isolated participant + job session. The existing load owner drives tick.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_participant_job_session~=true then return end
local ffi=require('ffi');ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);double GetCurrentGameTime(void);]]
local failed=false;local participant_busy=false;local participant,participant_net,job,job_net_owner,engine,next_hello=nil,nil,nil,nil,nil,0
local netlib,motion,client_authority=nil,nil,nil
local function fail(reason)
 if not failed then
  failed=true
  if type(reason)~='string' or #reason>64 or not reason:match('^[a-z0-9_]+$') then reason='session_tick' end
  DebugError('[X4LAN] AUTH_PARTICIPANT_JOB ERROR '..reason)
 end
end
function X4LAN_PARTICIPANT_JOB_TICK()
 if failed then return end
 if participant_busy then fail('reentrant');return end
 participant_busy=true
 local ok=pcall(function()
  assert(ffi.C.IsPlayerValid())
  if not participant then
   engine=assert(X4LAN_AUTHORITY_X4_CONTROL_ENGINE.new({enabled=true,test_profile='45841'}))
   local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))();netlib=lib
   participant_net=lib.open('127.0.0.1',cfg.authority_participant_port)
   local job_net=lib.open('127.0.0.1',cfg.authority_job_client_port)
   participant=assert(X4LAN_AUTHORITY_CONTROL_STATE.new({enabled=true,owner='isolated-client',
    world_epoch=cfg.authority_ticket.world_epoch,timeout_seconds=cfg.authority_job_client_timeout},engine,function(row)
     assert(participant_net:send('RECEIPT|'..cfg.authority_participant_lease..'|'..cfg.authority_ticket.world_epoch..'|'..
      string.format('%.0f',row.request_id)..'|'..row.operation..'|'..row.status))
    end))
   job_net_owner=job_net
  end
  local now=GetCurRealTime()
  if now>=next_hello then
   assert(participant_net:send('HELLO|'..cfg.authority_participant_lease..'|'..cfg.authority_ticket.world_epoch))
   next_hello=now+.25
  end
  for _=1,16 do
   local packet=participant_net:receive();if not packet then break end
   local lease,epoch,id,op=packet:match('^CMD|([0-9a-f]+)|([0-9a-f]+)|(%d+)|([a-z]+)$')
   assert(lease==cfg.authority_participant_lease and epoch==cfg.authority_ticket.world_epoch)
   assert(id and #id<=16 and not id:match('^0') and (op=='pause' or op=='resume'))
   -- This bounded owner cannot coordinate a pause with an armed/running job.
   assert(not job or op~='pause')
   assert(participant:submit('isolated-client',epoch,tonumber(id),op))
  end
  assert(participant:on_update())
  if not job and not ffi.C.IsGamePaused() then
   local game=tonumber(ffi.C.GetCurrentGameTime());assert(game and game>=0 and game<math.huge)
   DebugError('[X4LAN] AUTH_PARTICIPANT_JOB RUNNING '..string.format('%.17g',game))
   job=assert(X4LAN_AUTHORITY_JOB_CLIENT_OWNER.new_x4({enabled=true,
    lease=cfg.authority_job_client_lease,attempt=cfg.authority_job_client_attempt,
    epoch=cfg.authority_job_client_epoch,generation=cfg.authority_job_client_generation,
    nonce=cfg.authority_job_client_nonce,baseline=cfg.authority_job_client_baseline,
    seed=cfg.authority_job_client_seed,timeout=cfg.authority_job_client_timeout,position_tolerance=2,
    expected_save_path=cfg.authority_load_save_path,net=job_net_owner,
    client=X4LAN_MULTI_CREATE_CLIENT,inspector_module=X4LAN_MULTI_CREATE_INSPECTOR,resolve=X4LAN_RESOLVE_STRING,
    witness=function(sector)return cfg.authority_job_client_witnesses[sector]end,
    witness_audit=function(index,sector,witness,eligible)
     if not (type(index)=='number' and index>=1 and index%1==0 and
       type(witness)=='number' and witness>=1 and witness%1==0 and
       type(sector)=='string' and sector:match('^[A-Za-z0-9_]+$') and
       type(eligible)=='boolean') then return false end
     DebugError('[X4LAN] AUTH_WITNESS_PROBE '..string.format('%.0f',index)..' '..sector..' '..
      string.format('%.0f',witness)..' '..(eligible and '1' or '0'))
     return true
    end,
    guard=function()return not failed end,fault=fail,
    audit=function(index)
     local game=tonumber(ffi.C.GetCurrentGameTime());if not game or game<0 or game>=math.huge then return false end
     DebugError('[X4LAN] AUTH_PARTICIPANT_JOB LOCAL_APPLIED '..string.format('%.0f',index)..' '..string.format('%.17g',game))
     return true
    end}))
   assert(job:start())
  end
  if job then
   assert(job:tick())
   if cfg.authority_motion_client_enabled==true and not motion and job:state()=='ready' then
    local motion_net=netlib.open('127.0.0.1',cfg.authority_motion_client_port)
    local saved
    if cfg.authority_motion_client_saved_enabled==true then
     local epoch,baseline=cfg.authority_motion_client_epoch,cfg.authority_job_client_baseline
     saved={enabled=true,baseline=baseline,binding=X4LAN_SAVED_BASELINE_MOTION_BINDING,guard=function(e,b)
      return not failed and job:state()=='ready' and not ffi.C.IsGamePaused() and e==epoch and b==baseline and
       type(X4LAN_AUTHORITY_MARKER_READY)=='function' and X4LAN_AUTHORITY_MARKER_READY()==true and
       not failed and job:state()=='ready' and not ffi.C.IsGamePaused()
     end}
    end
    local saved_apply
    if cfg.authority_motion_apply_enabled==true then
     assert(saved and type(X4LAN_SAVED_MOTION_APPLY)=='table')
     saved_apply={enabled=true,module=X4LAN_SAVED_MOTION_APPLY,
      immediate_readback=cfg.authority_motion_apply_immediate_readback,observe_limit=cfg.authority_motion_apply_observe_limit,log=function(line)
      if type(line)~='string' or #line>512 or not line:match('^[%w%._%+%- ]+$') then return false end
      local kind=line:match('^(%u+[%u_]*) ')
      if kind~='INTENT' and kind~='WRITE_ENTERED' and kind~='IMMEDIATE' and kind~='POST_OBSERVED' and kind~='READBACK' and kind~='PREFLIGHT' then return false end
      DebugError('[X4LAN] AUTH_MOTION_APPLY '..line)
      return true
     end}
    end
    motion=assert(X4LAN_MOTION_CLIENT_OWNER.new_x4({enabled=true,net=motion_net,
     lease=cfg.authority_motion_client_lease,attempt=cfg.authority_motion_client_attempt,
     epoch=cfg.authority_motion_client_epoch,generation=cfg.authority_motion_client_generation,
     nonce=cfg.authority_motion_client_nonce,timeout=cfg.authority_motion_client_timeout,
     max_age=cfg.authority_motion_client_max_age,max_tracks=cfg.authority_motion_client_max_tracks,
     expected_save_path=cfg.authority_load_save_path,resolve=X4LAN_RESOLVE_STRING,
     binding=X4LAN_REPLICA_MOTION_BINDING,buffer=X4LAN_MOTION_BUFFER,saved_baseline=saved,saved_apply=saved_apply,
     guard=function()return not failed and job:state()=='ready' end,fault=fail,
     audit=function(index,sequence,sector,source_time)
      if type(index)~='number' or type(sequence)~='number' or type(sector)~='string' or not sector:match('^[A-Za-z0-9_]+$') or
         type(source_time)~='number' or source_time~=source_time then return false end
      DebugError('[X4LAN] AUTH_PARTICIPANT_MOTION BUFFERED '..string.format('%.0f',index)..' '..
       string.format('%.0f',sequence)..' '..sector..' '..string.format('%.17g',source_time))
      return true
     end}))
    assert(motion:start())
   end
   if motion then
    if job:state()=='ready' then assert(motion:tick())
    elseif motion:state()=='pending' or motion:state()=='applying' or motion:state()=='preflighting' then error('concurrent job and motion') end
   end
   if cfg.authority_client_authority_test~=nil and not client_authority and job:state()=='ready' then
    local x=cfg.authority_client_authority_test
    local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
    assert(type(x)=='table' and x.enabled==true and type(x.grant)=='function' and
     type(x.port)=='number' and x.port%1==0 and x.port>0 and x.port<=65535 and
     x.port~=cfg.authority_participant_port and x.port~=cfg.authority_job_client_port and x.port~=cfg.authority_motion_client_port)
    assert(token(x.lease) and token(x.attempt) and token(x.bootstrap_nonce) and token(x.sampler_nonce) and
     token(x.token) and token(x.incarnation) and x.lease~=x.attempt and x.token~=x.incarnation)
    assert(type(X4LAN_CLIENT_AUTHORITY_MOTION_SESSION)=='table' and type(X4LAN_CLIENT_AUTHORITY_MOTION_READER)=='table' and
     type(X4LAN_AUTHORITY_SOURCE_MOTION_IPC)=='table' and type(X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP)=='table' and
     type(X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER)=='table' and type(X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE)=='table')
    local e,g,grant_token,incarnation,grant,world=cfg.authority_job_client_epoch,cfg.authority_job_client_generation,x.token,x.incarnation,x.grant,cfg.authority_ticket.world_epoch
    local values={e,g,world,x.lease,x.attempt,x.bootstrap_nonce,x.sampler_nonce,grant_token,incarnation};local seen={}
    for _,value in ipairs(values)do assert(token(value) and not seen[value]);seen[value]=true end
    assert(x.bootstrap_nonce:sub(1,16)~=x.sampler_nonce:sub(1,16))
    local auth_net=assert(netlib.open('127.0.0.1',x.port))
    client_authority=assert(X4LAN_CLIENT_AUTHORITY_MOTION_SESSION.new_x4({enabled=true,epoch=e,generation=g,index=1318,
     baseline=cfg.authority_job_client_baseline,sector='cluster_115_sector001_macro',lease=x.lease,attempt=x.attempt,
     bootstrap_nonce=x.bootstrap_nonce,sampler_nonce=x.sampler_nonce,timeout=x.timeout,interval=x.interval,net=auth_net,
     reader=X4LAN_CLIENT_AUTHORITY_MOTION_READER,ipc=X4LAN_AUTHORITY_SOURCE_MOTION_IPC,
     bootstrap=X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP,sampler=X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER,
     descriptor=X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE,resolve=X4LAN_RESOLVE_STRING,expected_save_path=cfg.authority_load_save_path,
     event_register=function(callback)
      return RegisterEvent('X4AuthorityJobDescriptorProbe.Result',function(_,value)
       if failed then return end
       if participant_busy then fail('reentrant');return end
       participant_busy=true;local ok=pcall(callback,nil,value);participant_busy=false
       if not ok then fail('authority_event')end
      end)~=false
     end,
     guard=function()
      return not failed and job:state()=='ready' and not ffi.C.IsGamePaused() and
       (not motion or motion:state()=='ready') and type(X4LAN_AUTHORITY_MARKER_READY)=='function' and
       X4LAN_AUTHORITY_MARKER_READY()==true and not failed and job:state()=='ready' and not ffi.C.IsGamePaused() and
       (not motion or motion:state()=='ready')
     end,
     grant=function(a,b,i)return a==e and b==g and i==1318 and grant(a,b,i,grant_token,incarnation,world)==true end,
     audit=function(index,sequence,sector,t,px,py,pz)
      if index~=1318 or type(sequence)~='number' or sequence<1 or sequence%1~=0 or sector~='cluster_115_sector001_macro' then return false end
      for _,v in ipairs({t,px,py,pz})do if type(v)~='number' or v~=v or v==math.huge or v==-math.huge then return false end end
      DebugError(('[X4LAN] AUTH_CLIENT_AUTHORITY SAMPLE %d %d %s %.17g %.17g %.17g %.17g'):format(index,sequence,sector,t,px,py,pz))
      return true
     end,fault=fail}))
    assert(client_authority:start())
   end
   if client_authority then assert(client_authority:tick())end
  end
 end)
 participant_busy=false
 if not ok then fail() end
end
