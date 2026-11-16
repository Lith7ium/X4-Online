-- Compose real source IPC and shutdown gate; transport and game are doubles.
local B=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local S=dofile('src/authority/lua/source_motion_sampler.lua')
local G=dofile('src/authority/lua/source_motion_shutdown.lua')
local I=dofile('src/authority/lua/source_motion_ipc.lua')
local lease,attempt,epoch,gen=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32)
local function rig(pending)
 local input,out,faults={},{},{};local nonce=string.rep('e',32)
 local boot=assert(B.new({enabled=true,epoch=epoch,nonce=nonce,baseline=2,timeout=2,clock=function()return 1 end,
  guard=function()return true end,baseline_guard=function()return true end,issue=function()return true end,
  parse=function()return 1 end,inspect=function()return true end,complete=function()return true end}))
 local sampler=assert(S.new({enabled=true,epoch=epoch,generation=gen,nonce=nonce,max_tracks=2,scan_budget=1,
  interval=1,timeout=2,min_dt=.1,max_dt=1,clock=function()return 1 end,guard=function()return true end,
  binding_guard=function()return true end,actor_key=function()return '1'end,reader_factory=function()error('unexpected')end,fault=function()end}))
 local life=assert(G.new({enabled=true,bootstrap=boot,sampler=sampler,guard=function()return true end,
  quiescent=function()return true end,route=function()return true end,fault=function(v)faults[#faults+1]=v end}))
 if pending then assert(boot:begin(1))end
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
 local ipc=assert(I.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,
  timeout=5,clock=function()return 1 end,guard=function()return true end,net=net,
  stop=function()return life:stop()end,fault=function(v)faults[#faults+1]=v end}))
 assert(ipc:start());input[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..gen;assert(ipc:tick())
 input[1]='P|'..lease..'|'..attempt..'|STOP|'..epoch..'|'..gen..'|1'
 return ipc,life,boot,sampler,out,faults
end
do
 local ipc,life,b,s,out,faults=rig(false)
 assert(ipc:tick() and ipc:state()=='stopped' and life:state()=='stopped')
 assert(b:state()=='closed' and s:state()=='closed' and out[#out]:find('|STOPPED|',1,true))
 assert(not life:event('late') and life:state()=='failed' and #faults==1)
end
do
 local ipc,life,b,s,out,faults=rig(true)
 assert(not ipc:tick() and ipc:state()=='failed' and life:state()=='failed')
 assert(b:state()=='pending' and s:state()=='ready' and #faults>=1)
 for _,v in ipairs(out)do assert(not v:find('|STOPPED|',1,true))end
end
