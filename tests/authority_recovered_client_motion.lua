-- Actual Lua router/owner/binder with fake X4 ABI, MD and local net.
local ffi=require('ffi');ffi.cdef[[void TestPause(bool);]]
local handlers,requests,input,out,logs={}, {}, {}, {}, {}
function RegisterEvent(name,cb)assert(not handlers[name]);handlers[name]=cb;return true end
function GetCurRealTime()return 1 end
function AddUITriggeredEvent(screen,op,args)requests[#requests+1]={screen=screen,op=op,args=args};return true end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)assert(ref==41);return false,false,false end
function DebugError(v)logs[#logs+1]=v end
function X4LAN_RECOVERED_CLIENT_LOAD_READY()return true end
local race_value=nil;local receives=0
local net={send=function(_,v)out[#out+1]=v;return true end,pending=function()
 if race_value then input[1]=race_value;race_value=nil;return false end
 return #input>0
end,receive=function()
 receives=receives+1
 local v=table.remove(input,1);if v=='' or (v and #v>768)then return nil end;return v
end}
package.loadlib=function()return function()return {open=function(_,port)assert(port==2345);return net end}end end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_REPLICA_MOTION_BINDING=dofile('src/authority/lua/replica_motion_binding.lua')
X4LAN_SAVED_BASELINE_MOTION_BINDING=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
X4LAN_MOTION_BUFFER=dofile('src/authority/lua/motion_buffer.lua')
local buffered={};local new_buffer=X4LAN_MOTION_BUFFER.new
X4LAN_MOTION_BUFFER.new=function(options)
 local track=new_buffer(options);local push=track.push
 function track:push(sample,arrival)
  local ok=push(self,sample,arrival);if ok then buffered[#buffered+1]=sample end;return ok
 end
 return track
end
X4LAN_CLIENT_MOTION_EVENT_ROUTER=dofile('src/authority/lua/client_motion_event_router.lua')
X4LAN_MOTION_CLIENT_OWNER=dofile('src/authority/lua/motion_client_owner.lua')
local module=dofile('tools/dev/authority_recovered_client_motion.lua')
local l,a,e,g,n,rg=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32),('e'):rep(32),('1'):rep(32)
assert(module.new_x4({})==nil)
local incomplete={enabled=true,port=2345,lease=l,epoch=e,generation=g,nonce=n,router_generation=rg,
 baseline=100,index=42,timeout=2,expected_save_path='/private/45841/save'}
assert(not pcall(module.new_x4,incomplete))
local list_mode=arg[1]:find('list_',1,true)==1
local options={enabled=true,port=2345,lease=l,attempt=a,epoch=e,generation=g,nonce=n,router_generation=rg,
 baseline=100,timeout=2,expected_save_path='/private/45841/save'}
if list_mode then options.indices={42,43} else options.index=42 end
local owner=assert(module.new_x4(options))
if list_mode then options.indices[1]=44 end -- list is copied at construction
local idx=(arg[1]=='wrong_index' or arg[1]=='list_second') and 43 or (arg[1]=='list_unknown' and 44 or 42)
input[1]=table.concat({'M',l,a,'BIND',('f'):rep(32),e,g,tostring(idx),'1','sector_a',('9'):rep(64),'10','1','2','3','-','-','-'},'|')
if arg[1]=='wrong_index' or idx==44 then assert(not owner:tick() and owner:state()=='failed' and logs[#logs]:find('ERROR',1,true));return end
assert(owner:tick());local first=requests[#requests];assert(first.screen=='X4AuthoritySavedBaselineMotionBind')
handlers['X4AuthoritySavedBaselineMotionBind.Result'](nil,first.args.request_id..'|Bound|'..idx..'|0x29|0x2b')
assert(owner:state()=='ready' and out[#out]:find('|BOUND|',1,true))
if arg[1]=='list_switch' or arg[1]=='list_second' then
 local other=idx==42 and '43' or '42'
 input[1]=table.concat({'M',l,a,'BIND',('7'):rep(32),e,g,other,'2','sector_a',('9'):rep(64),'11','1','2','3','1','0','0'},'|')
 assert(not owner:tick() and owner:state()=='failed');return
end
if arg[1]=='list_good' then
 input[1]=table.concat({'M',l,a,'BIND',('7'):rep(32),e,g,'42','2','sector_a',('9'):rep(64),'11','1','2','3','1','0','0'},'|')
 assert(owner:tick());local second=requests[#requests]
 handlers['X4AuthoritySavedBaselineMotionBind.Result'](nil,second.args.request_id..'|Bound|42|0x29|0x2b')
 assert(owner:state()=='ready' and out[#out]:find('|BOUND|',1,true))
 assert(#buffered==2 and buffered[1].rate==nil and buffered[2].rate[1]==1 and buffered[2].rate[2]==0 and buffered[2].rate[3]==0)
end
input[1]=table.concat({'M',l,a,'STOP',('8'):rep(32),e,g},'|')
local mode=arg[1]
local bad=mode:find('empty',1,true) and '' or ('x'):rep(769)
if mode=='queued_empty' or mode=='queued_oversize' then
 input[2]=bad;assert(not owner:tick() and owner:state()=='failed')
 for _,v in ipairs(out)do assert(not v:find('|STOPPED|',1,true))end
 return
end
assert(owner:tick() and owner:state()=='stopped' and out[#out]:find('|STOPPED|',1,true))
ffi.C.TestPause(true)
if mode=='race_empty' or mode=='race_oversize' then
 race_value=bad;local before=receives
 assert(owner:tick() and receives==before and #input==1)
 assert(not owner:tick() and owner:state()=='failed');return
end
if mode=='late_empty' or mode=='late_oversize' then
 input[1]=bad;assert(not owner:tick() and owner:state()=='failed');return
end
assert(owner:tick())
handlers['X4AuthoritySavedBaselineMotionBind.Result'](nil,first.args.request_id..'|Bound|42|0x29|0x2b')
assert(owner:state()=='failed' and logs[#logs]:find('ERROR',1,true) and not owner:tick())
print('recovered client motion checks passed')
