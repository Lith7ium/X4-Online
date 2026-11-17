-- Real recovered source owner and UDP, with test-only X4/MD substitutes.
local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local netlib=assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')),'luaopen_x4lan_net'))()
local net=assert(netlib.open('127.0.0.1',assert(tonumber(os.getenv('TEST_NET_PORT')))))
local M=dofile('tools/dev/authority_recovered_source_motion.lua')
local B=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local S=dofile('src/authority/lua/source_motion_sampler.lua')
local I=dofile('src/authority/lua/source_motion_ipc.lua')
local G=dofile('src/authority/lua/source_motion_shutdown.lua')
local Pair=dofile('src/authority/lua/source_motion_local_pair.lua')
local epoch,gen='4ba7be438ebb04ec5bb85fdb95b5a488',('d'):rep(32)
local pending,handler={},nil
local sample_count=0
local app=assert(M.new({enabled=true,epoch=epoch,generation=gen,nonce=('3'):rep(32),saved_nonce=('5'):rep(32),baseline=10054,
 running=function()return true end,guard=function()return true end,clock=netlib.monotonic,timeout=5,
 local_pair={nonce=('6'):rep(32),index=1318,delivery=true,factory=Pair.new,report=function()return true end},
 register=function(f)handler=f;return true end,
 fault=function(reason)io.stderr:write(tostring(reason)..'\n');os.exit(1)end,
 bootstrap_factory=function(o)
  o.timeout=5;o.clock=netlib.monotonic
  o.issue=function(_,_,v)pending[#pending+1]={kind='bootstrap',args=v};return true end
  o.parse=function(v)return v end;o.inspect=function()return true end
  return B.new(o)
 end,
 sampler_factory=function(o)
  o.clock=netlib.monotonic;o.max_tracks=1;o.scan_budget=1;o.interval=.01;o.timeout=5;o.min_dt=.02;o.max_dt=2
  o.actor_key=function()return '41'end
  o.reader_factory=function(row,actor,request)
   return {start=function()pending[#pending+1]={kind='sample',request=request};return true end,
    tick=function()return true end,response=function()
     sample_count=sample_count+1;assert(sample_count<=2)
     local t=1+(sample_count-1)*.5
     return true,{epoch=epoch,index=row.index,sequence=row.sequence,descriptor_atomic=false,sector_identity_proven=false,
      sector_macro='cluster_06_sector001_macro',local_sector_key='43',game_before_pose=t,game_after_pose=t,x=9+sample_count,y=2,z=3}
    end}
  end
  return S.new(o)
 end,
 ipc_factory=function(o)
  o.enabled=true;o.lease=('1'):rep(32);o.attempt=('2'):rep(32);o.epoch=epoch;o.generation=gen
  o.timeout=5;o.clock=netlib.monotonic;o.net=net;return I.new(o)
 end,shutdown_factory=G.new}))
while true do
 assert(app:tick(),'source owner fault')
 while #pending>0 do
  local row=table.remove(pending,1)
  if row.kind=='bootstrap' then
   handler(row.args.request_id..'|'..epoch..'|'..row.args.index..'|ok|0x29|ship_arg_m_trans_container_02_b_macro|antigone|0x2b|cluster_06_sector001_macro')
  else handler(row.request..'|ok') end
 end
 ffi.C.usleep(1000)
end
