local ffi=require('ffi');ffi.cdef[[void TestReset(void);void TestUnpause(void);void TestAdvance(double);]]
local E,L=string.rep('a',32),string.rep('b',32)
local function run(mode)
 ffi.C.TestReset();local q,out,logs,order={},{},{},{};local state='new';local got
 X4LAN_CONFIG={authority_source_single_job_session=true,authority_source_control_port=1234,authority_source_job_port=1235,
  authority_source_control_lease=L,authority_ticket={world_epoch=E},authority_load_save_path='/private/45841/save',
  authority_source_host_timeout=10,authority_source_baseline=10054}
 local ctl={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(q,1)end}
 local job={}
 package.loadlib=function()return function()return {open=function(_,port)return port==1234 and ctl or job end}end end
 X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
 X4LAN_AUTHORITY_CONTROL_STATE={new=function(_,_,report)return {
  submit=function(_,who,epoch,id,op)assert(who=='isolated-source' and epoch==E and id==1 and op=='resume');order[#order+1]='submit';return true end,
  on_update=function()order[#order+1]='control';return true end}end}
 X4LAN_AUTHORITY_SOURCE_SINGLE_JOB_OWNER={new_x4=function(c)
  got=c;return {start=function()state='binding';return true end,state=function()return state end,
    tick=function()order[#order+1]='source';return true end}
 end}
 X4LAN_AUTHORITY_JOB_REGISTRY_HOST={};X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={};X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE={}
 X4LAN_RESOLVE_STRING={};X4LAN_AUTHORITY_SOURCE_JOB_IPC={};X4LAN_AUTHORITY_JOB_DELIVERY={}
 function GetCurRealTime()return 1 end
 function DebugError(s)logs[#logs+1]=s end
 dofile('tools/dev/authority_source_single_job_session.lua');X4LAN_SOURCE_SINGLE_JOB_TICK()
 assert(got.net==job and got.index==10055 and got.sequence==1 and #out==1)
 q[1]='CMD|'..L..'|'..E..'|1|resume'
 if mode~='early' then state='observing' end
 X4LAN_SOURCE_SINGLE_JOB_TICK()
 if mode=='early' then assert(logs[#logs]:match('ERROR') and not table.concat(order,','):match('submit'));return end
 assert(table.concat(order,',')=='control,source,submit,control,source')
 q[1]='CMD|'..L..'|'..E..'|2|resume';X4LAN_SOURCE_SINGLE_JOB_TICK()
 assert(logs[#logs]:match('ERROR') and table.concat(order,',')=='control,source,submit,control,source')
end
run('early');run('success')

-- Couple the real session, X4 source owner, IPC and delivery gate. The host,
-- MD descriptor, transport and X4 ABI are simulated; no game is started.
do
 ffi.C.TestReset()
 local lease,attempt,epoch,generation,request=string.rep('c',32),string.rep('d',32),string.rep('e',32),string.rep('f',32),string.rep('1',32)
 local peer=string.rep('2',32);local control_in,job_in,job_out,control_out,logs={},{},{},{},{}
 local phase='attached_wait_running';local host_cfg,callback,selected,source_acked
 X4LAN_CONFIG={authority_source_single_job_session=true,authority_source_control_port=1234,authority_source_job_port=1235,
  authority_source_control_lease=L,authority_ticket={world_epoch=E},authority_load_save_path='/private/45841/save',
  authority_source_lease=lease,authority_source_attempt=attempt,authority_source_epoch=epoch,authority_source_generation=generation,
  authority_source_descriptor_request=request,authority_source_host_timeout=5,authority_source_timeout=20,
  authority_source_window=5,authority_source_capacity=4,authority_source_baseline=10054}
 local ctl={send=function(_,v)control_out[#control_out+1]=v;return true end,receive=function()return table.remove(control_in,1)end}
 local job={send=function(_,v)job_out[#job_out+1]=v;return true end,receive=function()return table.remove(job_in,1)end}
 package.loadlib=function()return function()return {open=function(_,port)return port==1234 and ctl or job end}end end
 X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
 X4LAN_AUTHORITY_CONTROL_STATE={new=function()return {
  submit=function(_,who,world,id,op)
   assert(who=='isolated-source' and world==E and id==1 and op=='resume')
   ffi.C.TestUnpause();ffi.C.TestAdvance(1);return true
  end,on_update=function()return true end}end}
 X4LAN_AUTHORITY_JOB_REGISTRY_HOST={new_x4=function(c)host_cfg=c;return {
  start=function()return true end,state=function()return phase end,
  tick=function()if selected then selected=false;phase='await_delivery';assert(c.report({epoch=epoch,sequence=1,index=10055,
   classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false},41))end;return true end,
  confirm_delivery=function(_,e,s,i)assert(e==epoch and s==1 and i==10055);phase='front';source_acked=true;return true end}
 end}
 X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={}
 X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE={new_x4=function()return {
  start=function()return true end,tick=function()return true end,response=function()return true,
   {epoch=epoch,sequence=1,index=10055,macro='ship_a',owner='argon',sector_macro='sector_a',x=1,y=2,z=3,
    descriptor_atomic=false,sector_identity_proven=false,birth_confirmed=false}end}end}
 X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
 X4LAN_AUTHORITY_SOURCE_JOB_IPC=dofile('src/authority/lua/source_job_ipc.lua')
 X4LAN_AUTHORITY_JOB_DELIVERY=dofile('src/authority/lua/job_delivery.lua')
 X4LAN_AUTHORITY_SOURCE_SINGLE_JOB_OWNER=dofile('src/authority/lua/source_single_job_owner.lua')
 function RegisterEvent(_,cb)callback=cb;return true end
 function ConvertIDTo64Bit(v)return v end
 function GetCurRealTime()return 1 end
 function DebugError(s)logs[#logs+1]=s end
 dofile('tools/dev/authority_source_single_job_session.lua')
 local function tick()X4LAN_SOURCE_SINGLE_JOB_TICK();assert(not (logs[#logs] or ''):match('ERROR'))end
 tick();assert(job_out[#job_out]=='S|'..lease..'|'..attempt..'|HELLO|'..epoch..'|'..generation)
 job_in[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..generation;tick();tick()
 assert(job_out[#job_out]=='S|'..lease..'|'..attempt..'|ATTACHED|'..epoch..'|'..generation)
 job_in[1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..generation;tick()
 assert(job_out[#job_out]=='S|'..lease..'|'..attempt..'|GO_READY|'..epoch..'|'..generation)
 control_in[1]='CMD|'..L..'|'..E..'|1|resume';tick()
 selected=true;tick();callback(nil,'descriptor')
 assert(job_out[#job_out]:find('|CANDIDATE|',1,true) and not source_acked)
 local id=epoch..'|'..generation..'|1|10055'
 job_in[1]='P|'..lease..'|'..attempt..'|BIND|'..id..'|1|peer_1|'..peer;tick()
 assert(job_out[#job_out]=='S|'..lease..'|'..attempt..'|READY|'..id and not source_acked)
 job_in[1]='P|'..lease..'|'..attempt..'|RECEIPT|'..id..'|peer_1|'..peer;tick();assert(source_acked)
 phase='waiting';assert(host_cfg.queue_acked(epoch,1,10055));tick()
 assert(job_out[#job_out]=='S|'..lease..'|'..attempt..'|SOURCE_ACKED|'..id..'|peer_1|'..peer)
 job_in[1]='P|'..lease..'|'..attempt..'|REARM|'..id;tick()
 assert(job_out[#job_out]=='S|'..lease..'|'..attempt..'|REARMED|'..id)
end
