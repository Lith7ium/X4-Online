-- Synthetic integration: real Lua source host/probe + delivery gate, fake MD
-- and two fake clients. No X4, transport, native replication or descriptor proof.
local host_module=dofile('tools/dev/authority_job_registry_host.lua')
local probe=dofile('tools/dev/authority_job_registry_probe.lua')
local delivery=dofile('src/authority/lua/job_delivery.lua')
local epoch,generation=string.rep('a',32),string.rep('b',32)
local peers={{id='linux',incarnation=string.rep('c',32)}, {id='windows',incarnation=string.rep('d',32)}}
local handlers,queue,outbox,operations={},{},{},{}
local now,observed,acked,registered=0,1,0,0
local host,gate,fault,source_callback
local descriptor={macro='ship_test_macro',faction='faction_test',sector_macro='sector_test_macro',x=1,y=2,z=3}
local function emit(name,value) queue[#queue+1]={name,value} end
local function pump()
 while #queue>0 do
  local item=table.remove(queue,1);assert(handlers[item[1]],item[1])(nil,item[2])
 end
end
gate=assert(delivery.new({enabled=true,generation=generation,timeout=3,clock=function() return now end,
 membership=function() return peers end,
 send=function(peer,event) outbox[peer.id]={peer=peer,event=event};return true end,
 release=function(e,s,i) assert(e==epoch and s==1 and i==1);return host:confirm_delivery(e,s,i) end}))
local options={enabled=true,epoch=epoch,baseline={},capacity=4,window=1,timeout=2,
 defer_ack=true,delivery_timeout=4,probe=probe,
 register=function(name,fn) assert(not handlers[name]);handlers[name]=fn end,
 clock=function() return now end,can_observe=function() return true end,
 convert64=function(v) if type(v)=='table' then return v.id end return v end,
 to_lua_id=function(k) return {id=k} end,valid=function() return true end,
 report=function(row)
  assert(row.epoch==epoch and row.sequence==1 and row.index==1)
  return gate:begin({epoch=row.epoch,generation=generation,sequence=row.sequence,index=row.index,descriptor=descriptor})
 end,
 queue_acked=function(e,s,i) source_callback=(source_callback or 0)+1;return gate:source_acked(e,s,i) end,
 done=function() return true end,fault=function(reason) fault=reason end}
options.trigger=function(screen,op,args)
 operations[#operations+1]={screen=screen,op=op,args=args}
 if screen=='X4AuthorityShipRegistry' and op=='Initialize' then emit(screen..'.Initialized',epoch)
 elseif screen=='X4AuthorityShipRegistry' and op=='Enroll' then
  registered=registered+1;assert(registered==1);emit(screen..'.Enrolled',registered)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Initialize' then emit(screen..'.Initialized',epoch)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Status' then
  emit(screen..'.Epoch',epoch);emit(screen..'.Observed',observed);emit(screen..'.Acknowledged',acked)
  emit(screen..'.Depth',observed-acked);emit(screen..'.Inflight',0);emit(screen..'.Reason','');emit(screen..'.Healthy')
 elseif screen=='X4AuthorityJobShipEvents' and op=='Front' then
  assert(acked==0);emit(screen..'.Sequence',1);emit(screen..'.Actor',42)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Ack' then
  assert(args.epoch==epoch and args.sequence==1 and args.index==1)
  assert(acked==0);acked=1;emit(screen..'.Acked',1)
 elseif screen=='X4AuthorityJobShipEvents' and op=='Abort' then
  error('unexpected source abort')
 else error('unexpected request '..screen..'.'..op) end
 return true
end
host=assert(host_module.new(options));assert(host:start());pump()
assert(host:state()=='ready_front');assert(host:tick());pump()
assert(host:state()=='await_delivery' and gate:state()=='waiting')
assert(outbox.linux and outbox.windows and acked==0)
local function no_md_ack()
 for _,op in ipairs(operations) do assert(op.op~='Ack','source head was acknowledged prematurely') end
end
no_md_ack()
local ok,status=gate:ack(outbox.windows.peer,outbox.windows.event)
assert(ok and status=='pending' and acked==0 and gate:state()=='waiting');no_md_ack()
ok,status=gate:ack(outbox.windows.peer,outbox.windows.event)
assert(ok and status=='duplicate' and acked==0);no_md_ack()
ok,status=gate:ack(outbox.linux.peer,outbox.linux.event)
assert(ok and status=='released' and acked==1)
-- The fake MD has accepted the command, but its response has not been pumped.
assert(gate:state()=='released' and source_callback==nil and host:state()=='front')
pump()
assert(gate:state()=='idle' and source_callback==1 and host:state()=='waiting' and fault==nil)
print('synthetic two-client delivery host integration passed')
