-- Real Source session, baseline bootstrap/sampler and UDP with simulated X4 ABI/MD.
local ffi=require('ffi');ffi.cdef[[void TestReset(void);void TestUnpause(void);int usleep(unsigned int);]]
ffi.C.TestReset()
local epoch,gen=('a'):rep(32),('b'):rep(32)
local ml,ma,mn,dn=('1'):rep(32),('2'):rep(32),('3'):rep(32),('4'):rep(32)
local other={send=function()return true end,receive=function()return nil end}
local net=assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')),'luaopen_x4lan_net'))()
local ms=assert(net.open('127.0.0.1',assert(tonumber(os.getenv('TEST_NET_PORT')))))
package.loadlib=function()return function()return {open=function(_,p)return p==3333 and ms or other end}end end
X4LAN_CONFIG={authority_source_single_job_session=true,authority_source_control_port=1111,authority_source_job_port=2222,
 authority_source_control_lease=('f'):rep(32),authority_ticket={world_epoch=('c'):rep(32)},authority_load_save_path='/private/45841/save',
 authority_source_lease=('d'):rep(32),authority_source_attempt=('e'):rep(32),authority_source_epoch=epoch,authority_source_generation=gen,
 authority_source_descriptor_request=dn,authority_source_host_timeout=5,authority_source_timeout=30,authority_source_continuous=true,
 authority_source_window=10,authority_source_capacity=4,authority_source_baseline=10054,authority_source_motion_enabled=true,
 authority_source_motion_port=3333,authority_source_motion_lease=ml,authority_source_motion_attempt=ma,authority_source_motion_nonce=mn,
 authority_source_saved_baseline={enabled=true,via_ipc=true,nonce=('5'):rep(32),guard=function(e,b)return e==epoch and b==10054 end}}
X4LAN_AUTHORITY_SOURCE_SINGLE_JOB_OWNER={new_x4=function()return {start=function()return true end,state=function()return 'observing' end,tick=function()return true end}end}
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
X4LAN_AUTHORITY_CONTROL_STATE={new=function()return {on_update=function()return true end}end}
X4LAN_AUTHORITY_JOB_REGISTRY_HOST={};X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={}
local requests={};X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE={new_x4=function(c)return {
 start=function()requests[#requests+1]={kind='sample',request_id=c.request_id,row=c.row};return true end,
 tick=function()return true end,response=function(_,v)assert(v==c.request_id..'|ok');return true,
 {epoch=epoch,index=c.row.index,sequence=c.row.sequence,sector_macro='sector_a',x=-400,y=100000,z=500,
 game_before_pose=101,game_after_pose=101,local_sector_key='43',descriptor_atomic=false,sector_identity_proven=false}end}end}
X4LAN_AUTHORITY_SOURCE_JOB_IPC={};X4LAN_AUTHORITY_JOB_DELIVERY={}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER=dofile('src/authority/lua/source_motion_sampler.lua')
X4LAN_AUTHORITY_SOURCE_MOTION_IPC=dofile('src/authority/lua/source_motion_ipc.lua')
local router
function RegisterEvent(_,fn)assert(not router);router=fn;return true end
function AddUITriggeredEvent(_,_,args)requests[#requests+1]={kind='baseline',request_id=args.request_id,index=args.index};return true end
function ConvertIDTo64Bit(v)return v end
function ConvertStringToLuaID(v)return tonumber(v)end
function GetComponentData(_,key)if key=='macro' then return 'sector_a' end;return false,false,false end
function GetCurRealTime()return os.clock() end
function DebugError(v)if v:find('ERROR',1,true) then io.stderr:write(v..'\n');os.exit(1)end end
dofile('tools/dev/authority_source_single_job_session.lua');X4LAN_SOURCE_SINGLE_JOB_TICK();ffi.C.TestUnpause()
local answered=0
while true do
 X4LAN_SOURCE_SINGLE_JOB_TICK()
 while #requests>answered do
  answered=answered+1;local r=requests[answered]
  if r.kind=='baseline' then router(nil,r.request_id..'|'..epoch..'|'..r.index..'|ok|0x29|ship_a|argon|0x2b|sector_a')
  else router(nil,r.request_id..'|ok')end
 end
 ffi.C.usleep(1000)
end
