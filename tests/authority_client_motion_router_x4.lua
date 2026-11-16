-- Real local router + motion owner + saved/replica binders, fake X4 ABI and MD.
local ffi=require('ffi')
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local replica=dofile('src/authority/lua/replica_motion_binding.lua')
local saved=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
local buffer=dofile('src/authority/lua/motion_buffer.lua')
local core=dofile('src/authority/lua/motion_client_owner.lua')
local router_module=dofile('src/authority/lua/client_motion_event_router.lua')
local events,requests={},{};local permit=true;local router_permit=true;local confirmed=true;local faults={}
function RegisterEvent(name,cb)assert(not events[name]);events[name]=cb;return true end
function GetCurRealTime()return 1 end
function AddUITriggeredEvent(screen,op,args)requests[#requests+1]={screen=screen,op=op,args=args};return true end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)assert(ref==41);return false,false,false end
local router=assert(router_module.new_x4({enabled=true,max_generations=4,max_tracks=10,
 guard=function()return router_permit end,retire_guard=function()return confirmed end,fault=function(r)faults[#faults+1]=r end}))
assert(router:start())
assert(not pcall(core.new_x4,{enabled=true,binding=replica,event_router=router,router_generation=('1'):rep(32)}))
local epoch,lifetime=('c'):rep(32),('d'):rep(32)
local function make(lease,attempt,nonce,rg)
 local q,out={},{};local owner_faults={}
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(q,1)end}
 local owner=assert(core.new_x4({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=lifetime,nonce=nonce,
  router_generation=rg,event_router=router,timeout=2,max_age=2,max_tracks=10,guard=function()return permit end,
  net=net,fault=function(r)owner_faults[#owner_faults+1]=r end,stop=function()return true end,
  expected_save_path='/private/45841/save',resolve=resolve,binding=replica,buffer=buffer,
  saved_baseline={enabled=true,baseline=100,guard=function(e,n)return permit and e==epoch and n==100 end,binding=saved}}))
 return owner,q,out,owner_faults
end
local function bind(owner,q,lease,attempt,index,sequence)
 q[1]=table.concat({'M',lease,attempt,'BIND',('f'):rep(32),epoch,lifetime,tostring(index),tostring(sequence),'sector_a',('9'):rep(64),'10','1','2','3','-','-','-'},'|')
 assert(owner:tick());return requests[#requests]
end
local a,aq,ao=make(('a'):rep(32),('b'):rep(32),('e'):rep(32),('1'):rep(32))
assert(router:attach(('1'):rep(32),('e'):rep(32),epoch,a) and a:start())
local first=bind(a,aq,('a'):rep(32),('b'):rep(32),42,1)
assert(first.screen=='X4AuthoritySavedBaselineMotionBind' and first.args.baseline==100)
events['X4AuthoritySavedBaselineMotionBind.Result'](nil,first.args.request_id..'|Bound|42|0x29|0x2b')
assert(a:state()=='ready' and ao[#ao]:find('|BOUND|',1,true))
aq[1]=table.concat({'M',('a'):rep(32),('b'):rep(32),'STOP',('8'):rep(32),epoch,lifetime},'|')
assert(a:tick() and a:state()=='stopped' and ao[#ao]:find('|STOPPED|',1,true))
assert(router:retire())
local b,bq,bo,bf=make(('3'):rep(32),('4'):rep(32),('5'):rep(32),('2'):rep(32))
assert(router:attach(('2'):rep(32),('5'):rep(32),epoch,b) and b:start())
local index=arg[1]=='stale_same' and 42 or 101
local second=bind(b,bq,('3'):rep(32),('4'):rep(32),index,1)
if index==42 then assert(second.screen=='X4AuthoritySavedBaselineMotionBind' and second.args.baseline==100)
else assert(second.screen=='X4AuthorityReplicaMotionBind' and second.args.baseline==nil) end
if arg[1]=='stale' or arg[1]=='stale_same' then
 events['X4AuthoritySavedBaselineMotionBind.Result'](nil,first.args.request_id..'|Bound|42|0x29|0x2b')
 assert(router:state()=='failed' and b:state()=='pending' and #bo==1 and #faults==1)
else
 events['X4AuthorityReplicaMotionBind.Result'](nil,second.args.request_id..'|Bound|101|0x29|0x2b')
 assert(router:state()=='active' and b:state()=='ready' and bo[#bo]:find('|BOUND|',1,true))
 if arg[1]=='guard' then permit=false;assert(not b:tick() and b:state()=='failed')end
 if arg[1]=='router_guard' then router_permit=false;assert(not b:tick() and b:state()=='failed')end
 if arg[1]=='tamper' then router.issue=function()return true end;assert(not b:tick() and b:state()=='failed')end
end
print('routed client motion X4-double checks passed')
