-- Actual host/probe/source IPC/gate with synthetic MD, descriptor and transport.
-- No native X4 and no assertion that an activation is a birth.
local owner_module=dofile('src/authority/lua/source_single_job_owner.lua')
local host_module=dofile('tools/dev/authority_job_registry_host.lua')
local probe=dofile('tools/dev/authority_job_registry_probe.lua')
local ipc=dofile('src/authority/lua/source_job_ipc.lua')
local gate=dofile('src/authority/lua/job_delivery.lua')
local lease,attempt,epoch,generation,request=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32),string.rep('e',32)
local p1,p2=string.rep('1',32),string.rep('2',32)
local callbacks,md,out,incoming,ops={}, {}, {}, {}, {}
local running=false;local initialized=false;local acked=0;local now=1;local fault
local function emit(name,v)md[#md+1]={name,v}end
local function pump()while #md>0 do local q=table.remove(md,1);assert(callbacks[q[1]],q[1])(nil,q[2])end end
local net={}
function net:send(v)out[#out+1]=v;return true end
function net:receive()return table.remove(incoming,1)end
local function trigger(screen,op,args)
 ops[#ops+1]={screen,op,args}
 if screen=='X4AuthorityShipRegistry' and op=='Status' then emit(screen..'.Epoch',epoch);emit(screen..'.Count',2)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Status' and not initialized then emit(screen..'.Uninitialized')
 elseif screen=='X4AuthorityJobShipEvents' and op=='Initialize' then initialized=true;emit(screen..'.Initialized',epoch)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Status' then
  for _,x in ipairs({{'Epoch',epoch},{'Observed',1},{'Acknowledged',acked},{'Depth',1-acked},{'Inflight',0},{'Reason',''},{'Healthy',true}})do emit(screen..'.'..x[1],x[2])end
 elseif screen=='X4AuthorityJobShipEvents' and op=='Front' then emit(screen..'.Sequence',1);emit(screen..'.Actor',42)
 elseif screen=='X4AuthorityShipRegistry' and op=='Enroll' then assert(args.ship==42);emit(screen..'.Enrolled',3)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Ack' then assert(args.sequence==1 and args.index==3);acked=1;emit(screen..'.Acked',1)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Abort' then return true
 else error('unexpected '..screen..' '..op)end
 return true
end
local function host_factory(report,queue_acked,fail)
 return host_module.new({enabled=true,epoch=epoch,baseline={},capacity=4,window=20,timeout=5,
  attach_saved_registry=true,exclusive_registry_consumer=true,expected_last=2,can_attach=function()return not running end,
  defer_ack=true,delivery_timeout=15,queue_acked=queue_acked,expose_actor=true,probe=probe,
  register=function(name,fn)assert(not callbacks[name]);callbacks[name]=fn end,trigger=trigger,
  convert64=function(v)return v end,to_lua_id=function(v)return tonumber(v) end,valid=function(v)return v==42 end,
  clock=function()return now end,can_observe=function()return running end,report=report,done=function()return false end,fault=fail})
end
local desc_callback
local app=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
 descriptor_request=request,sequence=1,index=3,timeout=18,clock=function()return now end,guard=function()return true end,
 net=net,ipc=ipc,gate=gate,host_factory=host_factory,register_descriptor=function(fn)desc_callback=fn;return true end,
 descriptor_factory=function(r,a,id)
  assert(r.index==3 and a==42 and id==request)
  return {start=function()return true end,tick=function()return true end,response=function(_,v)
   assert(v=='descriptor')
   return true,{epoch=epoch,sequence=1,index=3,macro='ship_a',owner='argon',sector_macro='sector_a',x=1,y=2,z=3,
    descriptor_atomic=false,sector_identity_proven=false,birth_confirmed=false}
  end}
 end,fault=function(reason)fault=reason end}))
assert(app:start());assert(out[1]=='S|'..lease..'|'..attempt..'|HELLO|'..epoch..'|'..generation)
incoming[#incoming+1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..generation
assert(app:tick());pump();assert(app:tick());pump();assert(app:tick());pump()
assert(out[2]=='S|'..lease..'|'..attempt..'|ATTACHED|'..epoch..'|'..generation)
incoming[#incoming+1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..generation
assert(app:tick() and app:state()=='observing')
assert(out[#out]=='S|'..lease..'|'..attempt..'|GO_READY|'..epoch..'|'..generation);running=true
for _=1,5 do assert(app:tick());pump();if app:state()=='reading' then break end end
assert(app:state()=='reading' and acked==0);desc_callback(nil,'descriptor')
assert(app:state()=='delivering' and out[#out]:find('|CANDIDATE|',1,true))
local id=epoch..'|'..generation..'|1|3'
incoming[#incoming+1]='P|'..lease..'|'..attempt..'|BIND|'..id..'|2|peer_1|'..p1..'|peer_2|'..p2
assert(app:tick());assert(out[#out]=='S|'..lease..'|'..attempt..'|READY|'..id and acked==0)
incoming[#incoming+1]='P|'..lease..'|'..attempt..'|RECEIPT|'..id..'|peer_1|'..p1
assert(app:tick());assert(acked==0 and out[#out]=='S|'..lease..'|'..attempt..'|PARTIAL|'..id..'|peer_1|'..p1)
incoming[#incoming+1]='P|'..lease..'|'..attempt..'|RECEIPT|'..id..'|peer_2|'..p2
assert(app:tick());assert(acked==1);assert(not out[#out]:find('SOURCE_ACKED',1,true))
pump();assert(app:tick());assert(out[#out]=='S|'..lease..'|'..attempt..'|SOURCE_ACKED|'..id..'|peer_2|'..p2)
local opcount=#ops
for _=1,3 do now=now+.1;assert(app:tick())end
assert(#ops==opcount,'host must not consume another head before REARM')
incoming[#incoming+1]='P|'..lease..'|'..attempt..'|REARM|'..id
assert(app:tick());assert(app:state()=='done' and out[#out]=='S|'..lease..'|'..attempt..'|REARMED|'..id and not fault)
print('one held activation owner; synthetic source and two clients passed')
-- Wrong binding cannot start host or consume a queue event.
do
 local data,outbound={},{};local started=false;local why
 local n={send=function(_,v)outbound[#outbound+1]=v;return true end,receive=function()return table.remove(data,1)end}
 local fake={start=function()started=true;return true end,tick=function()return true end,state=function()return 'attached_wait_running'end,
  confirm_delivery=function()error('unexpected acknowledgement')end}
 local x=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
  descriptor_request=request,sequence=1,index=3,timeout=10,clock=function()return 1 end,guard=function()return true end,
  net=n,ipc=ipc,gate=gate,host_factory=function()return fake end,descriptor_factory=function()error('no descriptor')end,
  register_descriptor=function()return true end,fault=function(v)why=v end}))
 assert(x:start());data[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..string.rep('f',32)
 assert(not x:tick() and x:state()=='failed' and not started and why)
end
-- Existing registry entries never become a create candidate or an MD Ack.
do
 local data={};local report;local invoked=false
 local n={send=function()return true end,receive=function()return table.remove(data,1)end}
 local fake={start=function()return true end,tick=function()return true end,state=function()return 'attached_wait_running'end,
  confirm_delivery=function()invoked=true;return true end}
 local x=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
  descriptor_request=request,sequence=1,index=3,timeout=10,clock=function()return 1 end,guard=function()return true end,
  net=n,ipc=ipc,gate=gate,host_factory=function(r)report=r;return fake end,descriptor_factory=function()error('no descriptor')end,
  register_descriptor=function()return true end,fault=function()end}))
 assert(x:start());data[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..generation
 assert(x:tick() and x:tick() and x:state()=='await_go')
 data[1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..generation;assert(x:tick())
 assert(not report({epoch=epoch,sequence=1,index=3,classification='previously_unobserved_existing_index'},42))
 assert(x:state()=='failed' and not invoked)
end
-- Reentrant owner failure during IPC candidate guard must not leak a candidate.
do
 local data,output={},{};local report,descriptor_cb;local fire=false;local x
 local n={send=function(_,v)output[#output+1]=v;return true end,receive=function()return table.remove(data,1)end}
 local hs='attached_wait_running'
 local fake={start=function()return true end,state=function()return hs end,confirm_delivery=function()error('no ack')end,
  tick=function()if fire then fire=false;hs='await_delivery';assert(report({epoch=epoch,sequence=1,index=3,
   classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false},42))end;return true end}
 local desc={start=function()return true end,tick=function()return true end,response=function()return true,
  {epoch=epoch,sequence=1,index=3,macro='ship_a',owner='argon',sector_macro='sector_a',x=1,y=2,z=3,
   descriptor_atomic=false,sector_identity_proven=false,birth_confirmed=false}end}
 local reenter=false
 x=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
  descriptor_request=request,sequence=1,index=3,timeout=10,clock=function()return 1 end,
  guard=function()if reenter and x:state()=='delivering' then x:tick()end;return true end,
  net=n,ipc=ipc,gate=gate,host_factory=function(r)report=r;return fake end,descriptor_factory=function()return desc end,
  register_descriptor=function(cb)descriptor_cb=cb;return true end,fault=function()end}))
 assert(x:start());data[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..generation
 assert(x:tick() and x:tick());data[1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..generation
 assert(x:tick());fire=true;assert(x:tick() and x:state()=='reading')
 reenter=true;descriptor_cb(nil,'ok');assert(x:state()=='failed')
 for _,v in ipairs(output)do assert(not v:find('|CANDIDATE|',1,true))end
end
-- A reentrant descriptor registration cannot overwrite a failed state.
do
 local x
 local n={send=function()error('no send')end,receive=function()return nil end}
 local fake={confirm_delivery=function()return false end}
 x=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
  descriptor_request=request,sequence=1,index=3,timeout=10,clock=function()return 1 end,guard=function()return true end,
  net=n,ipc=ipc,gate=gate,host_factory=function()return fake end,descriptor_factory=function()return nil end,
  register_descriptor=function()x:tick();return true end,fault=function()end}))
 assert(not x:start() and x:state()=='failed')
end
-- Descriptor returned by reader is frozen across the next external guard.
do
 local data,output={},{};local report,descriptor_cb;local fire=false;local mutate=false
 local n={send=function(_,v)output[#output+1]=v;return true end,receive=function()return table.remove(data,1)end}
 local hs='attached_wait_running'
 local fake={start=function()return true end,state=function()return hs end,confirm_delivery=function()error('no ack')end,
  tick=function()if fire then fire=false;hs='await_delivery';assert(report({epoch=epoch,sequence=1,index=3,
   classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false},42))end;return true end}
 local value={epoch=epoch,sequence=1,index=3,macro='ship_a',owner='argon',sector_macro='sector_a',x=1,y=2,z=3,
  descriptor_atomic=false,sector_identity_proven=false,birth_confirmed=false}
 local desc={start=function()return true end,tick=function()return true end,response=function()mutate=true;return true,value end}
 local x=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
  descriptor_request=request,sequence=1,index=3,timeout=10,clock=function()return 1 end,
  guard=function()if mutate then value.macro='different' end;return true end,
  net=n,ipc=ipc,gate=gate,host_factory=function(r)report=r;return fake end,descriptor_factory=function()return desc end,
  register_descriptor=function(cb)descriptor_cb=cb;return true end,fault=function()end}))
 assert(x:start());data[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..generation
 assert(x:tick() and x:tick());data[1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..generation
 assert(x:tick());fire=true;assert(x:tick() and x:state()=='reading')
 descriptor_cb(nil,'ok');assert(x:state()=='failed')
 for _,v in ipairs(output)do assert(not v:find('|CANDIDATE|',1,true))end
end
-- An expired host attach must not yield a GO_READY, even when outer time remains.
do
 local data,outbound={},{};local expired=false
 local n={send=function(_,v)outbound[#outbound+1]=v;return true end,receive=function()return table.remove(data,1)end}
 local fake={start=function()return true end,tick=function()return not expired end,state=function()return 'attached_wait_running'end,
  confirm_delivery=function()error('no ack')end}
 local x=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
  descriptor_request=request,sequence=1,index=3,timeout=10,clock=function()return 1 end,guard=function()return true end,
  net=n,ipc=ipc,gate=gate,host_factory=function()return fake end,descriptor_factory=function()error('no descriptor')end,
  register_descriptor=function()return true end,fault=function()end}))
 assert(x:start());data[1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..generation
 assert(x:tick() and x:tick() and x:state()=='await_go');expired=true
 data[1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..generation
 assert(not x:tick() and x:state()=='failed')
 for _,v in ipairs(outbound)do assert(not v:find('|GO_READY|',1,true))end
end
