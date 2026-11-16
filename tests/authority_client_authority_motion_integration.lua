-- Actual local session + IPC + reader + saved bootstrap + sampler; fake MD/FFI.
local Session=dofile('src/authority/lua/client_authority_motion_session.lua')
local Reader=dofile('src/authority/lua/client_authority_motion_reader.lua')
local Bootstrap=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local Sampler=dofile('src/authority/lua/source_motion_sampler.lua')
local IPC=dofile('src/authority/lua/source_motion_ipc.lua')
local lease,attempt,epoch,generation=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32)
local input,out={},{};local now=1;local game=10;local rid,callback;local actor={}
local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
local session=assert(Session.new({enabled=true,epoch=epoch,generation=generation,index=1318,baseline=10054,
 guard=function()return true end,grant=function()return true end,fault=function()end,
 register=function(f)callback=f;return true end,ipc_factory=function(x)return IPC.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
 timeout=5,clock=function()return now end,guard=x.guard,fault=x.fault,net=net,saved_baseline={limit=10054,guard=function()return x.guard()end}})end,
 reader_factory=function(x)
  return Reader.new({enabled=true,epoch=epoch,generation=generation,index=1318,baseline=10054,sector='cluster_115_sector001_macro',
   bootstrap_nonce=('e'):rep(32),sampler_nonce=('f'):rep(32),guard=x.guard,authority=x.authority,stage_sample=x.stage_sample,fault=x.fault,
   bootstrap_factory=function(b)return Bootstrap.new({enabled=true,epoch=epoch,baseline=10054,nonce=b.nonce,timeout=5,clock=function()return now end,
    guard=x.guard,baseline_guard=function()return x.guard()end,issue=function(_,_,args)rid=args.request_id;return true end,
    parse=function(v)return v=='0x1' and actor or (v=='0x2' and {} or nil)end,inspect=function()return true end,complete=b.complete})end,
   sampler_factory=function(z)return Sampler.new({enabled=true,epoch=epoch,generation=generation,nonce=z.nonce,max_tracks=1,scan_budget=1,
    interval=.1,timeout=5,min_dt=.02,max_dt=1,clock=function()return now end,guard=x.guard,binding_guard=function()return false end,
    saved_baseline_limit=10054,saved_baseline_guard=z.saved_baseline_guard,actor_key=function(a)return a==actor and '1' or nil end,fault=z.fault,
    reader_factory=function(row,_,request)return {start=function()rid=request;return true end,tick=function()return true end,response=function()
     return true,{epoch=epoch,index=row.index,descriptor_atomic=false,sector_identity_proven=false,sector_macro='cluster_115_sector001_macro',
      local_sector_key='2',game_before_pose=game,game_after_pose=game,x=1,y=2,z=3}
    end}end})end})
 end}))
local suffix='|'..epoch..'|'..generation
assert(session:start());input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(session:tick())
input[1]='P|'..lease..'|'..attempt..'|REGISTER_SAVED'..suffix..'|1|1318|10054';assert(session:tick() and #out==2)
callback(nil,rid..'|'..epoch..'|1318|ok|0x1|ship_macro|owner|0x2|cluster_115_sector001_macro')
assert(#out==2 and session:tick() and out[3]:find('|SAVED_REGISTERED|',1,true))
input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|2';assert(session:tick() and #out==3)
callback(nil,rid..'|sample')
assert(out[4]=='S|'..lease..'|'..attempt..'|SAMPLE'..suffix..'|2|1318|1|cluster_115_sector001_macro|10|1|2|3|-|-|-')
print('client authority session/IPC/reader/bootstrap/sampler integrated')
