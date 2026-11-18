-- Real loader and recovery owners with fake LuaJIT platform and X4 APIs.
-- No native library, X4 instance, socket, or game state is touched.
local platform=assert(arg[1])
local expected={Linux='./extensions/x4_lan_lab/native/x4lan_net.so',
 Windows='./extensions/x4_lan_lab/native/x4lan_net_64.dll'}
local calls,errors,frame={}, {}, nil
local ffi={os=platform,NULL={},cdef=function()end,string=function(value)return value end,
 C={IsPlayerValid=function()return true end,IsGamePaused=function()return false end,
    GetSaveFolderPath=function()return '/private/45841/save' end}}
package.loaded.ffi=ffi
package.loadlib=function(path,symbol)
 calls[#calls+1]={path,symbol}
 assert(path==expected[platform] and symbol=='luaopen_x4lan_net')
 return function()return {monotonic=function()return 1 end,open=function(host,port)
  assert(host=='127.0.0.1' and port==2345)
  return {send=function()return true end,receive=function()return nil end,pending=function()return false end}
 end}end
end
X4LAN_LOCAL_UDP_MODULE=dofile('src/authority/lua/local_udp_module.lua')
X4LAN_CONFIG={authority_participant_port=2345,authority_participant_lease=('a'):rep(32),
 authority_ticket={world_epoch=('b'):rep(32)}}
function SetScript(name,fn)assert(name=='onUpdate' and not frame);frame=fn end
function DebugError(message)errors[#errors+1]=message end
function GetCurRealTime()return 1 end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return {}end}
X4LAN_AUTHORITY_CONTROL_STATE={new=function()return {on_update=function()return true end}end}
dofile('tools/dev/authority_two_x4_participant_probe.lua')
frame()
if not expected[platform] then
 assert(#calls==0 and #errors==1 and errors[1]:find('AUTH_PARTICIPANT ERROR',1,true))
else assert(#calls==1 and #errors==0)end

local router={start=function()return true end,attach=function()return true end,state=function()return 'active'end}
local owner={start=function()return true end,state=function()return 'ready'end}
X4LAN_CLIENT_MOTION_EVENT_ROUTER={new_x4=function()return router end}
X4LAN_MOTION_CLIENT_OWNER={new_x4=function()return owner end}
function X4LAN_RECOVERED_CLIENT_LOAD_READY()return true end
local motion=dofile('tools/dev/authority_recovered_client_motion.lua')
X4LAN_REPLICA_MOTION_BINDING=dofile('src/authority/lua/replica_motion_binding.lua')
local options={enabled=true,port=2345,baseline=100,index=42,timeout=5,
 lease=('a'):rep(32),attempt=('b'):rep(32),epoch=('c'):rep(32),generation=('d'):rep(32),
 nonce=('e'):rep(32),router_generation=('f'):rep(32),expected_save_path='/private/45841/save'}
local ok,result=pcall(motion.new_x4,options)
if expected[platform] then assert(ok and type(result)=='table' and #calls==2)
else assert(not ok and #calls==0)end
-- Relative paths remain invalid and must be rejected before loading.
options.expected_save_path='private/45841/save'
local before=#calls
assert(not pcall(motion.new_x4,options) and #calls==before)
