-- Real client authority Session/IPC/Reader/Bootstrap/Sampler and native UDP;
-- MD, component reads, authority and game time are fakes. No X4 runs.
local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local Session=dofile('src/authority/lua/client_authority_motion_session.lua')
local Reader=dofile('src/authority/lua/client_authority_motion_reader.lua')
local Bootstrap=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local Sampler=dofile('src/authority/lua/source_motion_sampler.lua')
local IPC=dofile('src/authority/lua/source_motion_ipc.lua')
local epoch,generation=('b'):rep(32),('c'):rep(32)
local lease,attempt=('1'):rep(32),('2'):rep(32)
local include_orientation=os.getenv('TEST_INCLUDE_ORIENTATION')=='1'
local netmod=assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')),'luaopen_x4lan_net'))()
local net=assert(netmod.open('127.0.0.1',assert(tonumber(os.getenv('TEST_NET_PORT')))))
local now,game=1,10;local rid,callback,reader;local actor={};local seen=nil;local boot_done=false
local session=assert(Session.new({enabled=true,epoch=epoch,generation=generation,index=1318,baseline=10054,
 guard=function()return true end,grant=function()return true end,fault=function(reason)error(reason)end,
 register=function(f)callback=f;return true end,ipc_factory=function(x)return IPC.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
 timeout=5,clock=function()return now end,guard=x.guard,fault=x.fault,net=net,saved_baseline={limit=10054,guard=function()return x.guard()end}})end,
 reader_factory=function(x)
  reader=Reader.new({enabled=true,epoch=epoch,generation=generation,index=1318,baseline=10054,sector='cluster_115_sector001_macro',
   include_orientation=include_orientation,
   bootstrap_nonce=('7'):rep(32),sampler_nonce=('8'):rep(32),guard=x.guard,authority=x.authority,stage_sample=x.stage_sample,fault=x.fault,
   bootstrap_factory=function(b)return Bootstrap.new({enabled=true,epoch=epoch,baseline=10054,nonce=b.nonce,timeout=5,clock=function()return now end,
    guard=x.guard,baseline_guard=function()return x.guard()end,issue=function(_,_,args)rid=args.request_id;return true end,
    parse=function(v)return v=='0x1' and actor or (v=='0x2' and {} or nil)end,inspect=function()return true end,complete=b.complete})end,
   sampler_factory=function(z)return Sampler.new({enabled=true,epoch=epoch,generation=generation,nonce=z.nonce,max_tracks=1,scan_budget=1,include_orientation=z.include_orientation,
    interval=.1,timeout=5,min_dt=.02,max_dt=1,clock=function()return now end,guard=x.guard,binding_guard=function()return false end,
    saved_baseline_limit=10054,saved_baseline_guard=z.saved_baseline_guard,actor_key=function(a)return a==actor and '1' or nil end,fault=z.fault,
    reader_factory=function(row,_,request)return {start=function()rid=request;return true end,tick=function()return true end,response=function()
     return true,{epoch=epoch,index=row.index,descriptor_atomic=false,sector_identity_proven=false,sector_macro='cluster_115_sector001_macro',
      local_sector_key='2',game_before_pose=game,game_after_pose=game,x=1,y=2,z=3,yaw=.1,pitch=.2,roll=.3}
    end}end})end})
  return reader
 end}))
assert(session:start())
while true do
 assert(session:tick())
 if rid and rid~=seen then
  seen=rid
  if not boot_done then
   callback(nil,rid..'|'..epoch..'|1318|ok|0x1|ship_macro|owner|0x2|cluster_115_sector001_macro');boot_done=true
  else callback(nil,rid..'|sample')end
  assert(session:state()=='ready')
 end
 now=now+.001;game=game+.001;ffi.C.usleep(1000)
end
