local ffi=require('ffi');ffi.cdef[[void TestReset(void);void TestUnpause(void);]];ffi.C.TestReset()
local epoch,lease=string.rep('a',32),string.rep('b',32)
X4LAN_CONFIG={authority_participant_job_session=true,authority_participant_port=1234,authority_job_client_port=1235,
 authority_participant_lease=lease,authority_ticket={world_epoch=epoch},authority_load_save_path='/private/45841/save',
 authority_job_client_timeout=10,authority_job_client_witnesses={sector_a=1}}
local sent,queue,order={}, {},{};local opened=0
local participant_net={send=function(_,s)sent[#sent+1]=s;return true end,receive=function()return table.remove(queue,1)end}
local job_net={};local motion_net={}
package.loadlib=function()return function()return {open=function(_,port)opened=opened+1;return port==1234 and participant_net or (port==1235 and job_net or motion_net) end}end end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
X4LAN_AUTHORITY_CONTROL_STATE={new=function(_,_,report)return {
 submit=function(_,owner,e,id,op)assert(owner=='isolated-client' and e==epoch and id==1 and op=='resume');order[#order+1]='submit';return true end,
 on_update=function()order[#order+1]='participant';ffi.C.TestUnpause();return true end}end}
X4LAN_AUTHORITY_JOB_CLIENT_OWNER={new_x4=function(c)
 assert(c.net==job_net and c.witness('sector_a')==1 and c.guard())
 return {state=function()return 'ready' end,start=function()order[#order+1]='start';return true end,tick=function()
  order[#order+1]='job'
  if os.getenv('TEST_CLIENT_FAULT')=='1' then c.fault('event_inspector_position');return false end
  if os.getenv('TEST_CLIENT_FAULT')=='2' then c.fault('secret/path');return false end
  return true
 end}
end}
X4LAN_REPLICA_MOTION_BINDING={}
X4LAN_MOTION_CLIENT_OWNER={new_x4=function(c)
 assert(c.net==motion_net and c.guard())
 return {start=function()order[#order+1]='motion_start';return true end,tick=function()order[#order+1]='motion';return true end,state=function()return 'ready' end}
end}
if os.getenv('TEST_MOTION_SESSION')=='1' then
 X4LAN_CONFIG.authority_motion_client_enabled=true;X4LAN_CONFIG.authority_motion_client_port=1236
end
function GetCurRealTime()return 1 end
local errors={}
function DebugError(s)errors[#errors+1]=s end
X4LAN_MULTI_CREATE_CLIENT={};X4LAN_MULTI_CREATE_INSPECTOR={};X4LAN_RESOLVE_STRING={}
dofile('tools/dev/authority_participant_job_session.lua')
queue[1]='CMD|'..lease..'|'..epoch..'|1|resume'
X4LAN_PARTICIPANT_JOB_TICK()
if os.getenv('TEST_MOTION_SESSION')=='1' then
 assert(opened==3 and table.concat(order,',')=='submit,participant,start,job,motion_start,motion')
 X4LAN_PARTICIPANT_JOB_TICK();assert(opened==3 and table.concat(order,',')=='submit,participant,start,job,motion_start,motion,participant,job,motion')
 return
end
if os.getenv('TEST_CLIENT_FAULT') then
 local expected=os.getenv('TEST_CLIENT_FAULT')=='1' and 'event_inspector_position' or 'session_tick'
 assert(#errors==2 and errors[2]=='[X4LAN] AUTH_PARTICIPANT_JOB ERROR '..expected)
 X4LAN_PARTICIPANT_JOB_TICK();assert(#errors==2);return
end
assert(opened==2 and sent[1]=='HELLO|'..lease..'|'..epoch)
assert(table.concat(order,',')=='submit,participant,start,job')
X4LAN_PARTICIPANT_JOB_TICK();assert(opened==2 and table.concat(order,',')=='submit,participant,start,job,participant,job')

queue[1]='CMD|'..lease..'|'..epoch..'|2|pause'
X4LAN_PARTICIPANT_JOB_TICK();assert(#errors==2 and errors[1]:match('RUNNING') and errors[2]:match('ERROR'))
assert(table.concat(order,',')=='submit,participant,start,job,participant,job' and #sent==1)
