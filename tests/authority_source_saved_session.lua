-- Real session, baseline bootstrap and sampler; simulated MD, control and C ABI.
local ffi=require('ffi');ffi.cdef[[void TestReset(void);void TestUnpause(void);]];ffi.C.TestReset()
local mode=arg[1];local epoch,gen,world=('a'):rep(32),('b'):rep(32),('c'):rep(32)
local lease,attempt,ctl,ml,ma,mn,dn=('d'):rep(32),('e'):rep(32),('f'):rep(32),('1'):rep(32),('2'):rep(32),('3'):rep(32),('4'):rep(32)
local queue,logs,router,issued={}, {},nil,nil;local registrations=0;local allowed=true;local calls=0;local attack_enabled=false
local function attack()
 if mode:find('_tick',1,true) then pcall(X4LAN_SOURCE_SINGLE_JOB_TICK)
 else pcall(router,nil,'foreign') end
end
local sock={send=function()return true end,receive=function()return nil end}
package.loadlib=function()return function()return {open=function()return sock end}end end
X4LAN_CONFIG={authority_source_single_job_session=true,authority_source_control_port=1111,authority_source_job_port=2222,
 authority_source_control_lease=ctl,authority_ticket={world_epoch=world},authority_load_save_path='/private/45841/save',
 authority_source_lease=lease,authority_source_attempt=attempt,authority_source_epoch=epoch,authority_source_generation=gen,
 authority_source_descriptor_request=dn,authority_source_host_timeout=5,authority_source_timeout=30,authority_source_continuous=true,
 authority_source_window=10,authority_source_capacity=4,authority_source_baseline=10054,authority_source_motion_enabled=true,
 authority_source_motion_port=3333,authority_source_motion_lease=ml,authority_source_motion_attempt=ma,authority_source_motion_nonce=mn,
 authority_source_saved_baseline={enabled=true,nonce=(mode=='collision' and mn or ('5'):rep(32)),
  guard=function(e,b)if attack_enabled and mode:find('guard_',1,true) then attack()end;return allowed and e==epoch and b==10054 end,
  next_index=function()if attack_enabled and mode:find('next_',1,true) then attack()end;return table.remove(queue,1)end}}
X4LAN_AUTHORITY_SOURCE_SINGLE_JOB_OWNER={new_x4=function()return {start=function()return true end,state=function()return 'observing' end,tick=function()return true end}end}
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
X4LAN_AUTHORITY_CONTROL_STATE={new=function()return {on_update=function()return true end}end}
X4LAN_AUTHORITY_JOB_REGISTRY_HOST={};X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={};X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE={new_x4=function()error('unexpected sampling')end}
X4LAN_AUTHORITY_SOURCE_JOB_IPC={};X4LAN_AUTHORITY_JOB_DELIVERY={}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local sampler=dofile('src/authority/lua/source_motion_sampler.lua');local original=sampler.new_x4
sampler.new_x4=function(c)
 local s=original(c);local register=s.register
 s.register=function(self,row,actor)registrations=registrations+1;return register(self,row,actor)end
 return s
end
X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER=sampler
X4LAN_AUTHORITY_SOURCE_MOTION_IPC={new=function()return {start=function()return true end,tick=function()return true end,requested=function()return false end}end}
function RegisterEvent(n,fn)assert(n=='X4AuthorityJobDescriptorProbe.Result' and not router);router=fn;return true end
function AddUITriggeredEvent(screen,op,args)assert(screen=='X4AuthorityJobDescriptorProbe' and op=='Read' and not issued);issued=args;return true end
function ConvertIDTo64Bit(v)return v end
function ConvertStringToLuaID(v)return tonumber(v)end
function GetComponentData(ref,key)
 if key=='macro' then return 'sector_a' end
 calls=calls+1
 if mode=='postcheck' and calls>=2 then return true,false,false end
 return false,false,false
end
function GetCurRealTime()return 1 end
function DebugError(v)logs[#logs+1]=v end
dofile('tools/dev/authority_source_single_job_session.lua')
X4LAN_SOURCE_SINGLE_JOB_TICK()
if mode=='collision' then assert(logs[#logs]:match('ERROR'));return end
assert(not (logs[#logs] or ''):match('ERROR'));ffi.C.TestUnpause();queue[1]=42
if mode:find('next_',1,true) then attack_enabled=true end
X4LAN_SOURCE_SINGLE_JOB_TICK()
if mode:find('next_',1,true) then assert(logs[#logs]:match('ERROR') and registrations==0 and not issued);return end
assert(issued and issued.index==42 and registrations==0)
if mode=='guard' then allowed=false end
if mode:find('guard_',1,true) then attack_enabled=true end
local id=mode=='foreign' and ('9'):rep(32) or issued.request_id
router(nil,id..'|'..epoch..'|42|ok|0x29|ship_a|argon|0x2b|sector_a')
if mode~='normal' then
 assert(logs[#logs]:match('ERROR') and registrations==0);X4LAN_SOURCE_SINGLE_JOB_TICK();assert(registrations==0);return
end
assert(not (logs[#logs] or ''):match('ERROR') and registrations==0)
X4LAN_SOURCE_SINGLE_JOB_TICK();assert(registrations==1 and not (logs[#logs] or ''):match('ERROR'))
allowed=false;queue[1]=43;X4LAN_SOURCE_SINGLE_JOB_TICK();assert(logs[#logs]:match('ERROR') and registrations==1)
