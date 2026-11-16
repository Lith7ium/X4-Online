-- Real owner/host/probe/gate; fake asynchronous MD, UDP and descriptors.
-- No game, TCP, process, ship creation, or native pause guarantee.
local owner=dofile('tools/dev/authority_census_job_owner.lua')
local hostmod=dofile('tools/dev/authority_job_registry_host.lua')
local probe=dofile('tools/dev/authority_job_registry_probe.lua')
local gate=dofile('src/authority/lua/job_delivery.lua')
local epoch,attempt,lease,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32)
local function run(mode,two)
 local handlers,events,input,output,ops={},{},{},{},{}
 local now,game,paused,queue_initialized=1,30,true,false
 local md_acked,started=false,false
 local app
 local function emit(screen,name,value)events[#events+1]={screen..'.'..name,value}end
 local function pump()
  while #events>0 do local e=table.remove(events,1);assert(handlers[e[1]],e[1])(nil,e[2])end
 end
 local net={send=function(_,v)output[#output+1]=v;return true end,receive=function()return table.remove(input,1)end,close=function()end}
 local opts={enabled=true,role='server',lease=lease,epoch=epoch,attempt=attempt,nonce=nonce,timeout=100,window=30,net=net,
  defer_ack=true,delivery=gate,clock=function()return now end,guard=function()return true end,
  observe=function()return paused,game end,pause=function()paused=true end,resume=function()paused=false;game=31 end,
  baseline_request=function()error('server baseline')end,log=function()end,
  descriptor_factory=function(row,actor)
   assert(row.index==10055 and actor==42)
   return {start=function()return true end,tick=function()return true end,close=function()return true end,
    response=function()return true,{epoch=epoch,index=10055,sequence=1,macro='ship_macro',owner='argon',sector_macro='sector_a',x=1,y=2,z=3}end}
  end,
  witness_factory=function(index,macro)return {start=function()return true end,tick=function()return true end,close=function()return true end,
   response=function()return true,{epoch=epoch,index=index,sector_macro=macro,local_witness_match=true}end}end}
 if two then opts.delivery_peers={{id='client1',incarnation=string.rep('e',32)},{id='client2',incarnation=string.rep('f',32)}} end
 opts.host_factory=function(report,fault,done,hold,queue_acked)
  local h={enabled=true,attach_saved_registry=true,exclusive_registry_consumer=true,expected_last=10054,
   epoch=epoch,baseline={},capacity=4,window=30,timeout=5,probe=probe,expose_actor=true,
   defer_ack=true,delivery_timeout=50,queue_acked=queue_acked,can_hold_delivery=hold,
   register=function(name,fn)assert(not handlers[name]);handlers[name]=fn end,
   convert64=function(v)return type(v)=='table' and v.id or v end,
   to_lua_id=function(v)return {id=v}end,valid=function()return true end,
   can_attach=function()return paused end,can_observe=function()return not paused end,clock=function()return now end,
   report=report,fault=fault,done=done}
  h.trigger=function(screen,operation,args)
   ops[#ops+1]=operation
   if screen=='X4AuthorityShipRegistry' and operation=='Status' then emit(screen,'Epoch',epoch);emit(screen,'Count',10054)
   elseif screen=='X4AuthorityJobShipEvents' and operation=='Status' and not queue_initialized then emit(screen,'Uninitialized')
   elseif screen=='X4AuthorityJobShipEvents' and operation=='Initialize' then queue_initialized=true;emit(screen,'Initialized',epoch)
   elseif screen=='X4AuthorityJobShipEvents' and operation=='Status' then
    emit(screen,'Epoch',epoch);emit(screen,'Observed',1);emit(screen,'Acknowledged',md_acked and 1 or 0)
    emit(screen,'Depth',md_acked and 0 or 1);emit(screen,'Inflight',0);emit(screen,'Reason','');emit(screen,'Healthy')
   elseif screen=='X4AuthorityJobShipEvents' and operation=='Front' then emit(screen,'Sequence',1);emit(screen,'Actor',42)
   elseif screen=='X4AuthorityShipRegistry' and operation=='Enroll' then emit(screen,'Enrolled',10055)
   elseif screen=='X4AuthorityJobShipEvents' and operation=='Ack' then
    assert(paused and args.epoch==epoch and args.sequence==1 and args.index==10055)
    md_acked=true;if mode~='missing_md_ack' then emit(screen,'Acked',1) end
   elseif screen=='X4AuthorityJobShipEvents' and operation=='Abort' then return true
   else error('unexpected '..screen..'.'..operation)end
   return true
  end
  return assert(hostmod.new(h))
 end
 app=assert(owner.new(opts));local cmd=table.concat({'CMD',lease,'server',attempt,epoch},'|')
 local function tick() local ok=app:tick();pump();return ok end
 assert(tick());assert(tick() and app:state()=='ready')
 input[1]=cmd..'|START'
 for _=1,12 do if app:state()=='descriptor_wait' then break end;assert(tick(),app:state()) end
 assert(app:state()=='descriptor_wait');assert(app:descriptor_event('ok'));assert(tick() and app:state()=='descriptor_sent')
 input[1]=cmd..'|WITNESS|1|41|sector_a';assert(tick());assert(app:witness_event('ok'));assert(tick() and app:state()=='finished')
 for _,op in ipairs(ops)do assert(op~='Ack')end
 if two then
  input[1]=cmd..'|DELIVERY_ACK|1|10055|client1|'..string.rep('e',32)
  assert(tick() and app:state()=='finished' and not md_acked and output[#output]:match('|PARTIAL_ACKED|1|10055|client1$'))
 end
 if mode=='pause_lost' then paused=false
 elseif mode=='game_changed' then game=32 end
 input[1]=cmd..(mode=='foreign_ack' and '|DELIVERY_ACK|2|10055' or '|DELIVERY_ACK|1|10055')..
  (two and '|client2|'..string.rep('f',32) or '')
 local accepted=tick()
 if mode=='pause_lost' or mode=='game_changed' or mode=='foreign_ack' then
  assert(not accepted and app:state()=='failed' and not md_acked)
 elseif mode=='missing_md_ack' then
  assert(accepted and app:state()=='ack_wait' and md_acked);now=10
  assert(not tick() and app:state()=='failed')
 else
  assert(accepted and md_acked and app:state()=='source_ack_pending')
  assert(tick() and app:state()=='source_acked' and output[#output]:match('|SOURCE_ACKED|1|10055$'))
 end
end
for _,mode in ipairs({'success','pause_lost','game_changed','foreign_ack','missing_md_ack'})do run(mode)end
for _,mode in ipairs({'success','pause_lost','game_changed','foreign_ack','missing_md_ack'})do run(mode,true)end
print('census deferred source integration passed')
