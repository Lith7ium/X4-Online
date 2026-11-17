-- X4 adapter wired to recovered owner with a synthetic ABI and fake MD.
local handlers,requests,logs={}, {}, {}
function RegisterEvent(name,callback) assert(not handlers[name]);handlers[name]=callback;return true end
function AddUITriggeredEvent(screen,operation,args)
 requests[#requests+1]={screen=screen,operation=operation,args=args};return true
end
function GetCurRealTime()return 1 end
function ConvertStringToLuaID(value)return tonumber(value)end
function ConvertIDTo64Bit(value)return value end
function GetComponentData(ref,key)assert(ref==43 and key=='macro');return 'sector_a' end
function DebugError(value)logs[#logs+1]=value end
function X4LAN_RECOVERED_CLIENT_LOAD_READY()return true end
X4LAN_LOCAL_UDP_MODULE={load=function()return {open=function()return {send=function()return true end,
 pending=function()return false end,receive=function()return nil end}end}end}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_PLAYER_SECTOR_INTEREST=dofile('src/authority/lua/player_sector_interest.lua')
X4LAN_CLIENT_MOTION_EVENT_ROUTER={new_x4=function()return {start=function()return true end,
 attach=function()return true end,state=function()return 'active' end}end}
local owner_fault
X4LAN_MOTION_CLIENT_OWNER={new_x4=function(options)owner_fault=options.fault;return {start=function()return true end,
 state=function()return 'ready' end,tick=function()return true end}end}
local recovered=dofile('tools/dev/authority_recovered_client_motion.lua')
local epoch,inc,nonce=('c'):rep(32),('2'):rep(32),('3'):rep(32)
local owner=assert(recovered.new_x4({enabled=true,port=2345,lease=('a'):rep(32),attempt=('b'):rep(32),
 epoch=epoch,generation=('d'):rep(32),nonce=('e'):rep(32),router_generation=('f'):rep(32),
 baseline=100,index=42,timeout=2,expected_save_path='/private/45841/save',
 player_sector={incarnation=inc,nonce=nonce}}))
if arg[1]=='untrusted_fault' then
 owner_fault('preflight_pre_response\nlease=secret')
 assert(owner:state()=='failed' and logs[#logs]=='[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR')
 return
end
assert(owner:tick() and #requests==1)
local request=requests[1]
assert(request.screen=='X4AuthorityPlayerSectorInterest' and request.operation=='Read')
handlers['X4AuthorityPlayerSectorInterest.Result'](nil,request.args.request_id..'|'..epoch..'|'..inc..'|ok|0x2b|sector_a')
assert(owner:state()=='ready' and #logs==1 and logs[1]=='[X4LAN] AUTH_CLIENT_SECTOR observed sector=sector_a')
handlers['X4AuthorityPlayerSectorInterest.Result'](nil,request.args.request_id..'|'..epoch..'|'..inc..'|ok|0x2b|sector_a')
assert(owner:state()=='failed' and logs[#logs]=='[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR reason=sector_event')
