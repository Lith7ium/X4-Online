-- Actual session, motion IPC, bootstrap and sampler; fake C ABI/MD/network.
local ffi=require('ffi');ffi.cdef[[void TestReset(void);void TestUnpause(void);]];ffi.C.TestReset()
local mode=arg[1];local epoch,gen,world=('a'):rep(32),('b'):rep(32),('c'):rep(32)
local lease,attempt,ctl,ml,ma,mn,dn=('d'):rep(32),('e'):rep(32),('f'):rep(32),('1'):rep(32),('2'):rep(32),('3'):rep(32),('4'):rep(32)
local input,out,logs,router,issued={},{},{},nil,nil;local registrations=0;local allowed=true;local clock,calls=1,0
local source_state,marker,control_input='observing',true,{}
local other={send=function()return true end,receive=function()return nil end}
local control={send=function()return true end,receive=function()return table.remove(control_input,1)end}
local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
package.loadlib=function()return function()return {open=function(_,p)return p==3333 and net or p==1111 and control or other end}end end
X4LAN_CONFIG={authority_source_single_job_session=true,authority_source_control_port=1111,authority_source_job_port=2222,
 authority_source_control_lease=ctl,authority_ticket={world_epoch=world},authority_load_save_path='/private/45841/save',
 authority_source_lease=lease,authority_source_attempt=attempt,authority_source_epoch=epoch,authority_source_generation=gen,
 authority_source_descriptor_request=dn,authority_source_host_timeout=5,authority_source_timeout=30,authority_source_continuous=true,
 authority_source_window=10,authority_source_capacity=4,authority_source_baseline=10054,authority_source_motion_enabled=true,
 authority_source_motion_port=3333,authority_source_motion_lease=ml,authority_source_motion_attempt=ma,authority_source_motion_nonce=mn,
 authority_source_saved_baseline={enabled=true,via_ipc=true,nonce=('5'):rep(32),guard=function(e,b)return allowed and e==epoch and b==10054 end}}
if mode:find('native_',1,true) then
 X4LAN_CONFIG.authority_source_saved_baseline=nil;X4LAN_CONFIG.authority_source_saved_enabled=true;X4LAN_CONFIG.authority_source_saved_nonce=('5'):rep(32)
end
function X4LAN_AUTHORITY_MARKER_READY()return marker end
X4LAN_AUTHORITY_SOURCE_SINGLE_JOB_OWNER={new_x4=function()return {start=function()return true end,state=function()return source_state end,tick=function()return true end}end}
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
X4LAN_AUTHORITY_CONTROL_STATE={new=function()return {on_update=function()return true end,submit=function()return true end}end}
X4LAN_AUTHORITY_JOB_REGISTRY_HOST={};X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={};X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE={new_x4=function()error('unexpected sampling')end}
X4LAN_AUTHORITY_SOURCE_JOB_IPC={};X4LAN_AUTHORITY_JOB_DELIVERY={}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local sampler=dofile('src/authority/lua/source_motion_sampler.lua');local original=sampler.new_x4
sampler.new_x4=function(c)
 local s=original(c);local register=s.register
 s.register=function(self,row,actor)registrations=registrations+1;if mode=='register_fail' then return false end;return register(self,row,actor)end
 return s
end
X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER=sampler
X4LAN_AUTHORITY_SOURCE_MOTION_IPC=dofile('src/authority/lua/source_motion_ipc.lua')
function RegisterEvent(n,fn)assert(n=='X4AuthorityJobDescriptorProbe.Result' and not router);router=fn;return true end
function AddUITriggeredEvent(screen,op,args)assert(screen=='X4AuthorityJobDescriptorProbe' and op=='Read' and not issued);issued=args;return true end
function ConvertIDTo64Bit(v)return v end
function ConvertStringToLuaID(v)return tonumber(v)end
function GetComponentData(_,key)
 if key=='macro' then return 'sector_a' end
 calls=calls+1;if mode=='postcheck' and calls>=2 then return true,false,false end
 return false,false,false
end
function GetCurRealTime()return clock end
function DebugError(v)logs[#logs+1]=v end
local function tick()X4LAN_SOURCE_SINGLE_JOB_TICK()end
local prefix='P|'..ml..'|'..ma..'|'
dofile('tools/dev/authority_source_single_job_session.lua');tick()
assert(out[#out]=='S|'..ml..'|'..ma..'|HELLO|'..epoch..'|'..gen)
input[1]=prefix..'BOUND|'..epoch..'|'..gen;tick();assert(out[#out]:find('|ATTACHED|',1,true));ffi.C.TestUnpause()
if mode:find('native_',1,true) then control_input[1]='CMD|'..ctl..'|'..world..'|1|resume';tick() end
local index=mode=='range' and '10055' or '42';local bound=mode=='baseline' and '10053' or '10054'
input[1]=prefix..'REGISTER_SAVED|'..epoch..'|'..gen..'|1|'..index..'|'..bound;tick()
if mode=='range' or mode=='baseline' then assert(logs[#logs]:match('ERROR') and not issued and registrations==0);return end
assert(issued and issued.index==42 and registrations==0 and not out[#out]:find('|SAVED_REGISTERED|',1,true))
if mode=='timeout' then clock=7;tick();assert(logs[#logs]:match('ERROR') and registrations==0 and not out[#out]:find('|SAVED_REGISTERED|',1,true));return end
if mode=='pending_packet' then input[1]=prefix..'PULL|'..epoch..'|'..gen..'|2';tick();assert(logs[#logs]:match('ERROR') and registrations==0 and not out[#out]:find('|SAVED_REGISTERED|',1,true));return end
if mode=='pending_register' then input[1]=prefix..'REGISTER_SAVED|'..epoch..'|'..gen..'|2|43|10054';tick();assert(logs[#logs]:match('ERROR') and registrations==0 and not out[#out]:find('|SAVED_REGISTERED|',1,true));return end
if mode=='guard' then allowed=false end
if mode=='native_job' then source_state='reading' end
if mode=='native_marker' then marker=false end
if mode=='deadline_response' then clock=7 end
local id=mode=='foreign' and ('9'):rep(32) or issued.request_id
router(nil,id..'|'..epoch..'|42|ok|0x29|ship_a|argon|0x2b|sector_a')
if mode=='guard' or mode=='foreign' or mode=='postcheck' or mode=='deadline_response' or mode=='native_job' or mode=='native_marker' then assert(logs[#logs]:match('ERROR') and registrations==0 and not out[#out]:find('|SAVED_REGISTERED|',1,true));return end
assert(registrations==0 and not out[#out]:find('|SAVED_REGISTERED|',1,true));tick()
if mode=='register_fail' then assert(logs[#logs]:match('ERROR') and registrations==1 and not out[#out]:find('|SAVED_REGISTERED|',1,true));return end
assert(registrations==1 and out[#out]=='S|'..ml..'|'..ma..'|SAVED_REGISTERED|'..epoch..'|'..gen..'|1|42|10054')
input[1]=prefix..'REGISTER_SAVED|'..epoch..'|'..gen..'|1|42|10054';tick()
assert(logs[#logs]:match('ERROR') and registrations==1)
