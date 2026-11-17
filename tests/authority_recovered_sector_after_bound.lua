-- Real motion/binding/router with a synthetic X4 ABI, UDP and sector reader.
local ffi=require('ffi');ffi.cdef[[void TestPause(bool);]]
local mode=assert(arg[1]);local handlers,requests,input,out,logs={}, {}, {}, {}, {}
function RegisterEvent(name,cb)assert(not handlers[name]);handlers[name]=cb;return true end
function GetCurRealTime()return 1 end
function AddUITriggeredEvent(screen,op,args)requests[#requests+1]={screen=screen,op=op,args=args};return true end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)assert(ref==41);return false,false,false end
function DebugError(v)logs[#logs+1]=v end
function X4LAN_RECOVERED_CLIENT_LOAD_READY()return true end
local net={send=function(_,v)
 if v:find('|BOUND|',1,true) then
  if mode=='send_failure' then return false end
  if mode=='failure_after_send' then ffi.C.TestPause(true)end
 end
 out[#out+1]=v;return true
end,pending=function()return #input>0 end,receive=function()return table.remove(input,1)end}
package.loadlib=function()return function()return {open=function()return net end,monotonic=function()return 1 end}end end
X4LAN_LOCAL_UDP_MODULE=dofile('src/authority/lua/local_udp_module.lua')
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_REPLICA_MOTION_BINDING=dofile('src/authority/lua/replica_motion_binding.lua')
X4LAN_SAVED_BASELINE_MOTION_BINDING=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
X4LAN_MOTION_BUFFER=dofile('src/authority/lua/motion_buffer.lua')
X4LAN_CLIENT_MOTION_EVENT_ROUTER=dofile('src/authority/lua/client_motion_event_router.lua')
X4LAN_MOTION_CLIENT_OWNER=dofile('src/authority/lua/motion_client_owner.lua')
if mode=='forged_ack' then
 X4LAN_MOTION_CLIENT_OWNER={new_x4=function(options)
  return {start=function()return true end,state=function()return 'ready'end,event=function()return true end,
   tick=function()
    local value=options.net:receive()
    if value then options.net:send('R|'..options.lease..'|'..options.attempt..'|BOUND|forged')end
    return true
   end}
 end}
end
local sector_requests=0
X4LAN_PLAYER_SECTOR_INTEREST={new_x4=function(options)
 local phase='idle'
 return {begin=function()assert(phase=='idle');sector_requests=sector_requests+1;phase='pending';return true end,
  tick=function()return phase=='pending'end,state=function()return phase end,
  event=function(_,value)
   assert(phase=='pending' and value=='ok')
   assert(options.complete({epoch=options.epoch,incarnation=options.incarnation,sequence=1,sector_macro='sector_a'}))
   phase='idle';return true
  end,close=function()phase='closed';return true end}
end}
local recovered=dofile('tools/dev/authority_recovered_client_motion.lua')
local l,a,e,g,n,rg=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32),('e'):rep(32),('1'):rep(32)
local owner=assert(recovered.new_x4({enabled=true,port=2345,lease=l,attempt=a,epoch=e,generation=g,nonce=n,
 router_generation=rg,baseline=100,index=42,timeout=2,expected_save_path='/private/45841/save',
 player_sector={incarnation=('2'):rep(32),nonce=('3'):rep(32),after_bound=true}}))
assert(owner:tick() and sector_requests==0)
local request_id=('f'):rep(32)
local function bind(index)
 return table.concat({'M',l,a,'BIND',request_id,e,g,index,'1','sector_a',('9'):rep(64),'10','1','2','3','-','-','-'},'|')
end
input[1]=bind(mode=='wrong_index' and '43' or '42')
if mode=='wrong_index' or mode=='forged_ack' then
 assert(not owner:tick() and owner:state()=='failed' and sector_requests==0)
 for _,value in ipairs(out)do assert(not value:find('|BOUND|',1,true))end
 return
end
assert(owner:tick() and sector_requests==0)
local request=requests[#requests];assert(request.screen=='X4AuthoritySavedBaselineMotionBind')
if mode=='duplicate' then input[1]=bind('42')end
handlers['X4AuthoritySavedBaselineMotionBind.Result'](nil,request.args.request_id..'|Bound|42|0x29|0x2b')
assert(sector_requests==0) -- No Read inside or before the event callback.
if mode=='duplicate' or mode=='send_failure' or mode=='failure_after_send' then
 assert(owner:state()=='failed' and not owner:tick() and sector_requests==0)
 return
end
local expected=table.concat({'R',l,a,'BOUND',request_id,e,g,'42','1','sector_a',('9'):rep(64)},'|')
assert(out[#out]==expected and owner:state()=='ready')
if mode=='stop_before_query' then
 input[1]=table.concat({'M',l,a,'STOP',('8'):rep(32),e,g},'|')
 assert(not owner:tick() and owner:state()=='failed' and sector_requests==0)
 return
end
assert(owner:tick() and sector_requests==1)
if mode=='stop_pending' then
 input[1]=table.concat({'M',l,a,'STOP',('8'):rep(32),e,g},'|')
 assert(not owner:tick() and owner:state()=='failed')
 return
end
handlers['X4AuthorityPlayerSectorInterest.Result'](nil,'ok')
assert(logs[#logs]=='[X4LAN] AUTH_CLIENT_SECTOR observed sector=sector_a')
input[1]=table.concat({'M',l,a,'STOP',('8'):rep(32),e,g},'|')
assert(owner:tick() and owner:state()=='stopped' and out[#out]:find('|STOPPED|',1,true))
handlers['X4AuthorityPlayerSectorInterest.Result'](nil,'ok')
assert(owner:state()=='failed' and sector_requests==1)
