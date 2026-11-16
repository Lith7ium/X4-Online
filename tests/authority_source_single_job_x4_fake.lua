local ffi=require('ffi')
ffi.cdef[[void TestReset(void);void TestUnpause(void);void TestPause(void);void TestAdvance(double);]]
local mod=dofile('src/authority/lua/source_single_job_owner.lua')
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local ipc=dofile('src/authority/lua/source_job_ipc.lua');local gate=dofile('src/authority/lua/job_delivery.lua')
local lease,attempt,epoch,gen,request=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32),string.rep('e',32)
local callback;function RegisterEvent(_,cb)callback=cb;return true end
function GetCurRealTime()return 1 end
function ConvertIDTo64Bit(x)return x end
local function build(external,on_send)
 local incoming,out={},{};local cfg,trigger,source_ack;local phase='attached_wait_running'
 local net={send=function(_,v)out[#out+1]=v;if on_send then on_send(v)end;return true end,receive=function()return table.remove(incoming,1)end}
 local host={new_x4=function(c)
  cfg=c
  return {start=function()return true end,state=function()return phase end,
   tick=function()
    if trigger then trigger=false;phase='await_delivery'
     assert(cfg.report({epoch=epoch,sequence=1,index=3,classification='new_registry_entry',
      birth_confirmed=false,delivery_confirmed=false},41))
    end;return true end,
   confirm_delivery=function(_,e,s,i)assert(e==epoch and s==1 and i==3);phase='front';return true end}
 end}
 local desc={new_x4=function()
  return {start=function()return true end,tick=function()return true end,response=function()
   return true,{epoch=epoch,sequence=1,index=3,macro='ship_a',owner='argon',sector_macro='sector_a',x=1,y=2,z=3,
    descriptor_atomic=false,sector_identity_proven=false,birth_confirmed=false}end}
 end}
 local fault
 local owner=assert(mod.new_x4({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,
  descriptor_request=request,sequence=1,index=3,timeout=10,host_timeout=5,window=5,capacity=4,
  expected_save_path='/private/45841/save',external_guard=external or function()return true end,
  fault=function(s)fault=s end,net=net,host=host,probe={},descriptor=desc,ipc=ipc,gate=gate,resolve=resolve}))
 return owner,incoming,out,function()trigger=true end,function()
  phase='waiting';assert(cfg.queue_acked(epoch,1,3))
 end,function()return fault end,function()return cfg.raw_actor_guard end
end
-- Raw event identity must remain exact before the registry can enroll it.
ffi.C.TestReset()
do
 local _,_,_,_,_,_,get_guard=build();local exact=get_guard()
 assert(not exact(9007199254740992));assert(exact(assert(resolve.parse_hex('0x20000000000001'))))
end
-- A context callback which unpauses before attach must invalidate the sample.
ffi.C.TestReset()
do
 local x=build(function()ffi.C.TestUnpause();return true end)
 assert(not x:start() and x:state()=='failed')
end
-- Paused-game time cannot advance during the binding handshake.
ffi.C.TestReset()
do
 local x=build();assert(x:start());ffi.C.TestAdvance(1)
 assert(not x:tick() and x:state()=='failed')
end
-- A supervisor can resume immediately after receiving GO_READY.
ffi.C.TestReset()
do
 local x,input=build(nil,function(v)
  if v:find('|GO_READY|',1,true)then ffi.C.TestUnpause();ffi.C.TestAdvance(1)end
 end)
 assert(x:start());input[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..gen
 assert(x:tick() and x:tick());input[1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..gen
 assert(x:tick() and x:state()=='observing')
end
-- The initial paused sample must progress; a pause after actual source Ack
-- still fences REARM even though host polling is intentionally suspended.
ffi.C.TestReset()
do
 local x,input,out,select_event,source_acked=build()
 assert(x:start());input[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..gen
 assert(x:tick() and x:tick());input[1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..gen
 assert(x:tick());ffi.C.TestUnpause();ffi.C.TestAdvance(1)
 select_event();assert(x:tick() and x:state()=='reading');callback(nil,'result')
 assert(x:state()=='delivering')
 local id=epoch..'|'..gen..'|1|3';local peer=string.rep('f',32)
 input[1]='P|'..lease..'|'..attempt..'|BIND|'..id..'|1|peer_1|'..peer
 assert(x:tick());input[1]='P|'..lease..'|'..attempt..'|RECEIPT|'..id..'|peer_1|'..peer
 assert(x:tick());source_acked();assert(x:tick())
 assert(out[#out]=='S|'..lease..'|'..attempt..'|SOURCE_ACKED|'..id..'|peer_1|'..peer)
 ffi.C.TestPause();input[1]='P|'..lease..'|'..attempt..'|REARM|'..id
 assert(not x:tick() and x:state()=='failed')
 for _,v in ipairs(out)do assert(not v:find('|REARMED|',1,true))end
end
-- No progress from the initial paused time means no descriptor/candidate.
ffi.C.TestReset()
do
 local x,input,out,select_event=build()
 assert(x:start());input[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..gen
 assert(x:tick() and x:tick());input[1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..gen
 assert(x:tick());ffi.C.TestUnpause();select_event()
 assert(not x:tick() and x:state()=='failed')
 for _,v in ipairs(out)do assert(not v:find('|CANDIDATE|',1,true))end
end
print('source X4 guard fake ABI checks passed')
