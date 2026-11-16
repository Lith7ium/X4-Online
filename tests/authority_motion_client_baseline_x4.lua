-- Actual owner + saved/replica binders, with fake X4 C ABI and MD events.
local ffi=require('ffi');ffi.cdef[[void TestPause(bool);]]
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local replica=dofile('src/authority/lua/replica_motion_binding.lua')
local saved=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
local buffer=dofile('src/authority/lua/motion_buffer.lua')
local core=dofile('src/authority/lua/motion_client_owner.lua')
local events,requests,input,out={}, {}, {}, {};local allowed=true
function RegisterEvent(name,cb)assert(events[name]==nil);events[name]=cb;return true end
function GetCurRealTime()return 1 end
function AddUITriggeredEvent(screen,op,args)requests[#requests+1]={screen=screen,args=args};return true end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)assert(ref==41);return false,false,false end
local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
local owner=assert(core.new_x4({enabled=true,lease=('a'):rep(32),attempt=('b'):rep(32),epoch=('c'):rep(32),generation=('d'):rep(32),nonce=('e'):rep(32),
 timeout=2,max_age=2,max_tracks=10,guard=function()return true end,net=net,fault=function()end,
 expected_save_path='/private/45841/save',resolve=resolve,binding=replica,buffer=buffer,
 saved_baseline={enabled=true,baseline=100,guard=function(epoch,n)return allowed and epoch==('c'):rep(32) and n==100 end,binding=saved}}))
assert(owner:start() and events['X4AuthoritySavedBaselineMotionBind.Result'] and events['X4AuthorityReplicaMotionBind.Result'])
local function apply(index,screen,event)
 input[1]=table.concat({'M',('a'):rep(32),('b'):rep(32),'BIND',('f'):rep(32),('c'):rep(32),('d'):rep(32),tostring(index),'1','sector_a',('1'):rep(64),'10','1','2','3','-','-','-'},'|')
 assert(owner:tick());local r=requests[#requests];assert(r.screen==screen and r.args.index==index)
 if index==42 then assert(r.args.baseline==100)else assert(r.args.baseline==nil)end
 events[event](nil,r.args.request_id..'|Bound|'..index..'|0x29|0x2b')
 assert(owner:state()=='ready' and out[#out]:find('|BOUND|',1,true))
end
apply(42,'X4AuthoritySavedBaselineMotionBind','X4AuthoritySavedBaselineMotionBind.Result')
apply(101,'X4AuthorityReplicaMotionBind','X4AuthorityReplicaMotionBind.Result')
assert(#out==3)
