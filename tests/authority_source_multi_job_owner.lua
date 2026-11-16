-- Actual FIFO host/probe + source IPC/gate, synthetic MD and two clients.
local scenario=arg[1] or 'bounded'
local continuous=scenario=='continuous' or scenario=='empty' or scenario=='long' or scenario=='many'
local event_count=scenario=='empty' and 0 or (scenario=='many' and 110 or 2)
local invalidate=false
local owner_module=dofile('src/authority/lua/source_single_job_owner.lua')
local host_module=dofile('tools/dev/authority_job_registry_host.lua')
local probe=dofile('tools/dev/authority_job_registry_probe.lua')
local ipc=dofile('src/authority/lua/source_job_ipc.lua')
local gate=dofile('src/authority/lua/job_delivery.lua')
local lease,attempt,epoch,gen,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32),string.rep('e',32)
local inc1,inc2=string.rep('1',32),string.rep('2',32)
local callbacks,md,out,incoming,ops,requests={},{},{},{},{},{}
local running=false;local initialized=false;local acked=0;local now=1;local fault
local function emit(name,v)md[#md+1]={name,v}end
local function pump()while #md>0 do local q=table.remove(md,1);assert(callbacks[q[1]],q[1])(nil,q[2])end end
local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(incoming,1)end}
local function trigger(screen,op,args)
 ops[#ops+1]={screen,op,args}
 if screen=='X4AuthorityShipRegistry' and op=='Status' then emit(screen..'.Epoch',epoch);emit(screen..'.Count',2)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Status' and not initialized then emit(screen..'.Uninitialized')
 elseif screen=='X4AuthorityJobShipEvents' and op=='Initialize' then initialized=true;emit(screen..'.Initialized',epoch)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Status' then
  for _,x in ipairs({{'Epoch',epoch},{'Observed',event_count},{'Acknowledged',acked},{'Depth',event_count-acked},{'Inflight',0},{'Reason',''},{'Healthy',true}})do emit(screen..'.'..x[1],x[2])end
 elseif screen=='X4AuthorityJobShipEvents' and op=='Front' then
  if acked==event_count then emit(screen..'.Empty') else
   assert(acked<event_count);emit(screen..'.Sequence',acked+1);emit(screen..'.Actor',42+acked)
  end
 elseif screen=='X4AuthorityShipRegistry' and op=='Enroll' then
  assert(args.ship==42+acked);emit(screen..'.Enrolled',(scenario=='known' and acked==1) and 3 or (3+acked))
 elseif screen=='X4AuthorityJobShipEvents' and op=='Ack' then
  assert(args.sequence==acked+1 and args.index==3+acked);acked=acked+1;emit(screen..'.Acked',acked)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Abort' then return true
 else error('unexpected '..screen..' '..op)end
 return true
end
local function host_factory(report,source_acked,fail,finish)
 return host_module.new({enabled=true,epoch=epoch,baseline={},capacity=128,window=scenario=='empty' and 1 or (scenario=='long' and 40 or (scenario=='many' and 180 or 25)),timeout=5,
  attach_saved_registry=true,exclusive_registry_consumer=true,expected_last=2,can_attach=function()return not running end,
  defer_ack=true,delivery_timeout=15,queue_acked=source_acked,expose_actor=true,probe=probe,
  register=function(n,fn)assert(not callbacks[n]);callbacks[n]=fn end,trigger=trigger,
  convert64=function(v)return v end,to_lua_id=function(v)return tonumber(v)end,valid=function(v)return v>=42 and v<42+event_count and not (invalidate and v==43) end,
  clock=function()return now end,can_observe=function()return running end,report=report,done=function(summary)return finish(summary)end,fault=fail})
end
local descriptor_cb
local app=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,
 descriptor_request=nonce,sequence=1,index=3,max_events=not continuous and 2 or nil,continuous=continuous,timeout=35,clock=function()return now end,guard=function()return true end,
 net=net,ipc=ipc,gate=gate,host_factory=host_factory,register_descriptor=function(fn)descriptor_cb=fn;return true end,
 descriptor_factory=function(r,a,id)
  assert(r.index==r.sequence+2 and a==r.sequence+41);requests[#requests+1]=id
  return {start=function()return true end,tick=function()return true end,response=function()
   return true,{epoch=epoch,sequence=r.sequence,index=r.index,macro='ship_a',owner='argon',sector_macro='sector_a',
    x=r.sequence,y=2,z=3,descriptor_atomic=false,sector_identity_proven=false,birth_confirmed=false}end}
 end,fault=function(reason)fault=reason end}))
local function tick()now=now+.11;assert(app:tick());pump()end
assert(app:start());incoming[#incoming+1]='P|'..lease..'|'..attempt..'|BOUND|'..epoch..'|'..gen
tick();tick();tick();incoming[#incoming+1]='P|'..lease..'|'..attempt..'|GO|'..epoch..'|'..gen;tick();running=true
if scenario=='empty' then
 for _=1,30 do if app:state()=='done' then break end;tick()end
 assert(app:state()=='done' and out[#out]=='S|'..lease..'|'..attempt..'|FINISHED|'..epoch..'|'..gen..'|0' and acked==0)
 print('empty observation is inconclusive');return
end
for n=1,event_count do
 if n==2 and scenario=='known' then
  for _=1,12 do
   if app:state()=='failed' then break end
   now=now+.11;app:tick();pump()
  end
  assert(app:state()=='failed' and acked==1 and #requests==1);print('known entry fenced');return
 end
 for _=1,12 do if app:state()=='reading' then break end;tick()end
 assert(app:state()=='reading' and acked==n-1)
 descriptor_cb(nil,'ok');assert(app:state()=='delivering')
 local id=epoch..'|'..gen..'|'..n..'|'..(n+2)
 assert(out[#out]:find('|CANDIDATE|'..id..'|',1,true))
 incoming[#incoming+1]='P|'..lease..'|'..attempt..'|BIND|'..id..'|2|peer_1|'..inc1..'|peer_2|'..inc2
 tick();assert(acked==n-1)
 incoming[#incoming+1]='P|'..lease..'|'..attempt..'|RECEIPT|'..id..'|peer_1|'..inc1
 tick();assert(acked==n-1)
 if scenario=='actor' and n==2 then
  invalidate=true;incoming[#incoming+1]='P|'..lease..'|'..attempt..'|RECEIPT|'..id..'|peer_2|'..inc2
  now=now+.11;assert(not app:tick() and app:state()=='failed' and acked==1);print('changed actor fenced');return
 end
 incoming[#incoming+1]='P|'..lease..'|'..attempt..'|RECEIPT|'..id..'|peer_2|'..inc2
 tick();assert(acked==n);tick()
 assert(out[#out]=='S|'..lease..'|'..attempt..'|SOURCE_ACKED|'..id..'|peer_2|'..inc2)
 if scenario=='overflow' and n==1 then
  callbacks['X4AuthorityJobShipEvents.Faulted'](nil,'overflow')
  assert(app:state()=='failed' and acked==1);print('overflow fenced');return
 end
 local oldops=#ops;for _=1,3 do tick()end;assert(#ops==oldops,'next head before REARM')
 incoming[#incoming+1]='P|'..lease..'|'..attempt..'|REARM|'..id;tick()
 assert(out[#out]=='S|'..lease..'|'..attempt..'|REARMED|'..id)
 assert(app:state()==((n<event_count or continuous) and 'observing' or 'done'))
end
if continuous then
 now=scenario=='long' and 43 or (scenario=='many' and 182 or 28)
 for _=1,8 do if app:state()=='done' then break end;tick()end
 assert(app:state()=='done' and out[#out]=='S|'..lease..'|'..attempt..'|FINISHED|'..epoch..'|'..gen..'|'..event_count)
end
local unique={}
for _,id in ipairs(requests)do assert(#id==32 and not unique[id]);unique[id]=true end
assert(#requests==event_count and not fault and acked==event_count)
print('two FIFO heads delivered with per-event request IDs')
