-- Actual shared X4 session + job owner/IPC/gate + motion sampler/IPC, with
-- simulated MD/host/control/network and fake C ABI; no X4 process is started.
local ffi=require('ffi');ffi.cdef[[void TestReset(void);void TestUnpause(void);void TestAdvance(double);]]
ffi.C.TestReset()
local source_mod=dofile('src/authority/lua/source_single_job_owner.lua')
local motion_mod=dofile('src/authority/lua/source_motion_sampler.lua')
local motion_ipc=dofile('src/authority/lua/source_motion_ipc.lua')
local job_ipc=dofile('src/authority/lua/source_job_ipc.lua');local gate=dofile('src/authority/lua/job_delivery.lua')
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local epoch,gen,world=string.rep('a',32),string.rep('b',32),string.rep('c',32)
local lease,attempt,ctl=string.rep('d',32),string.rep('e',32),string.rep('f',32)
local ml,ma,mn,dn=string.rep('1',32),string.rep('2',32),string.rep('3',32),string.rep('4',32)
local peer=string.rep('5',32)
local ci,ji,mi,co,jo,mo,logs,requests={},{},{},{},{},{},{},{}
local function socket(input,output)return {send=function(_,v)output[#output+1]=v;return true end,receive=function()return table.remove(input,1)end}end
local cs,js=socket(ci,co),socket(ji,jo)
local net=assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')),'luaopen_x4lan_net'))()
local ms=assert(net.open('127.0.0.1',assert(tonumber(os.getenv('TEST_NET_PORT')))))
package.loadlib=function()return function()return {open=function(_,p)if p==1111 then return cs elseif p==2222 then return js elseif p==3333 then return ms end end}end end
X4LAN_CONFIG={authority_source_single_job_session=true,authority_source_control_port=1111,authority_source_job_port=2222,
 authority_source_control_lease=ctl,authority_ticket={world_epoch=world},authority_load_save_path='/private/45841/save',
 authority_source_lease=lease,authority_source_attempt=attempt,authority_source_epoch=epoch,authority_source_generation=gen,
 authority_source_descriptor_request=dn,authority_source_host_timeout=5,authority_source_timeout=30,authority_source_continuous=true,
 authority_source_window=10,authority_source_capacity=4,authority_source_baseline=10054,
 authority_source_motion_enabled=true,authority_source_motion_port=3333,authority_source_motion_lease=ml,
 authority_source_motion_attempt=ma,authority_source_motion_nonce=mn}
X4LAN_AUTHORITY_SOURCE_SINGLE_JOB_OWNER=source_mod;X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER=motion_mod
X4LAN_AUTHORITY_SOURCE_MOTION_IPC=motion_ipc;X4LAN_AUTHORITY_SOURCE_JOB_IPC=job_ipc;X4LAN_AUTHORITY_JOB_DELIVERY=gate
X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={};X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
X4LAN_AUTHORITY_CONTROL_STATE={new=function()return {submit=function(_,who,w,id,op)
 assert(who=='isolated-source' and w==world and id==1 and op=='resume');ffi.C.TestUnpause();ffi.C.TestAdvance(1);return true end,
 on_update=function()return true end}end}
local host_cfg,phase,select_actor=nil,'attached_wait_running',nil
X4LAN_AUTHORITY_JOB_REGISTRY_HOST={new_x4=function(c)host_cfg=c;return {start=function()return true end,state=function()return phase end,
 tick=function()if select_actor then local n=select_actor;select_actor=nil;phase='await_delivery';assert(c.report({epoch=epoch,index=10054+n,sequence=n,
  classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false},40+n))end;return true end,
 confirm_delivery=function(_,e,s,i)assert(e==epoch and s==1 and i==10055);phase='front';return true end}end}
X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE={new_x4=function(c)
 return {start=function()requests[#requests+1]=c;return true end,tick=function()return true end,response=function(_,v)
  assert(v==c.request_id..'|ok')
  local t=tonumber(ffi.C.GetCurrentGameTime())
  return true,{epoch=epoch,index=c.row.index,sequence=c.row.sequence,sector_macro='sector_a',macro='ship_a',owner='argon',
   x=-400,y=100000,z=500,game_before_pose=t,game_after_pose=t,local_sector_key=c.include_local_sector and '43' or nil,
   descriptor_atomic=false,sector_identity_proven=false,birth_confirmed=false}
 end}
end}
local router
function RegisterEvent(n,fn)assert(n=='X4AuthorityJobDescriptorProbe.Result' and not router);router=fn;return true end
function ConvertIDTo64Bit(v)return v end
function ConvertStringToLuaID(v)return tonumber(v)end
function GetComponentData()return false,false,false end
local clock=1
function GetCurRealTime()return clock end
function DebugError(v)logs[#logs+1]=v end
dofile('tools/dev/authority_source_single_job_session.lua')
local function tick()X4LAN_SOURCE_SINGLE_JOB_TICK();assert(not (logs[#logs] or ''):match('ERROR'))end
tick()
ji[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..gen;tick();tick()
ji[1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..gen;tick()
ci[1]='CMD|'..ctl..'|'..world..'|1|resume';tick()
select_actor=1;tick();router(nil,requests[1].request_id..'|ok')
local id=epoch..'|'..gen..'|1|10055'
ji[1]='P|'..lease..'|'..attempt..'|BIND|'..id..'|1|peer_1|'..peer;tick()
ji[1]='P|'..lease..'|'..attempt..'|RECEIPT|'..id..'|peer_1|'..peer;tick()
phase='waiting';assert(host_cfg.queue_acked(epoch,1,10055));tick()
ji[1]='P|'..lease..'|'..attempt..'|REARM|'..id;tick()
assert(jo[#jo]=='S|'..lease..'|'..attempt..'|REARMED|'..id)
io.stdout:write('CONFIRMED\n');io.stdout:flush()
ffi.cdef[[int usleep(unsigned int);]]
local answered=1
while true do
 tick()
 while #requests>answered do answered=answered+1;router(nil,requests[answered].request_id..'|ok') end
 ffi.C.usleep(1000)
end
