-- Synthetic MD event loop; no real X4 process or checkpoint.
local host=dofile('tools/dev/authority_job_registry_host.lua')
local probe=dofile('tools/dev/authority_job_registry_probe.lua')
local function scenario(kind)
 local handlers,queue,issued,rows={}, {}, {}, {}
 local t,paused,observed,ack=.0,true,3,0
 local epoch=string.rep('a',32);local done,fault
 local actors={11,22,11};local indices={2,10055,2}
 local function emit(screen,name,value) queue[#queue+1]={screen..'.'..name,value} end
 local opts={enabled=true,attach_saved_registry=true,exclusive_registry_consumer=true,expected_last=10054,
  epoch=epoch,baseline={},capacity=8,window=.6,timeout=.5,probe=probe,
  register=function(name,fn) assert(not handlers[name]);handlers[name]=fn end,
  convert64=function(v) if type(v)=='table' then return v.id end return v end,
  to_lua_id=function(k) return {id=k} end,valid=function() return true end,
  can_attach=function() return paused end,can_observe=function() return not paused end,clock=function() return t end,
  report=function(row) rows[#rows+1]=row;return true end,done=function(row) done=row;return true end,
  fault=function(reason) fault=reason end}
 opts.trigger=function(screen,operation,args)
  issued[#issued+1]={screen=screen,operation=operation,args=args}
  if kind=='timeout' and screen=='X4AuthorityShipRegistry' then return end
  if screen=='X4AuthorityShipRegistry' and operation=='Status' then
   if kind=='uninitialized' then emit(screen,'Uninitialized');return end
   if kind=='faulted' then emit(screen,'Faulted');return end
   emit(screen,'Epoch',kind=='wrong_epoch' and string.rep('b',32) or epoch)
   emit(screen,'Count',kind=='wrong_last' and 10053 or 10054)
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Status' and #issued==2 then
   if kind=='queue_existing' then emit(screen,'Epoch',epoch) else emit(screen,'Uninitialized') end
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Initialize' then emit(screen,'Initialized',epoch)
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Status' then
   emit(screen,'Epoch',epoch);emit(screen,'Observed',observed);emit(screen,'Acknowledged',ack)
   emit(screen,'Depth',observed-ack);emit(screen,'Inflight',0);emit(screen,'Reason','');emit(screen,'Healthy')
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Front' then
   if observed>ack then emit(screen,'Sequence',ack+1);emit(screen,'Actor',actors[ack+1]) else emit(screen,'Empty') end
  elseif screen=='X4AuthorityShipRegistry' and operation=='Enroll' then
   assert(type(args.ship)=='table' and args.ship.id==tostring(actors[ack+1]))
   emit(screen,'Enrolled',indices[ack+1])
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Ack' then
   assert(args.sequence==ack+1 and args.index==indices[ack+1]);ack=ack+1;emit(screen,'Acked',ack)
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Abort' then return
  else error('unexpected operation '..screen..'.'..operation) end
 end
 if kind=='not_paused' then paused=false end
 local app=host.new(opts);local ok=app:start()
 if kind=='not_paused' then assert(not ok);return app,issued,rows,done,fault end
 assert(ok)
 for _=1,80 do
  while #queue>0 do
   local event=table.remove(queue,1)
   if kind=='lost_pause' then paused=false end
   assert(handlers[event[1]])(nil,event[2])
  end
  if app:state()=='done' or app:state()=='failed' then break end
  if app:state()=='attached_wait_running' and kind~='resume_timeout' then paused=false end
  t=t+.11;app:tick()
 end
 return app,issued,rows,done,fault
end
local app,ops,rows,done,err=scenario('ok')
assert(app:state()=='done',tostring(err));assert(#rows==3)
assert(rows[1].index==2 and rows[1].classification=='previously_unobserved_existing_index')
assert(rows[2].index==10055 and rows[2].classification=='new_registry_entry')
assert(rows[3].index==2 and rows[3].classification=='previously_observed')
assert(done.baseline_count==10054 and done.baseline_known_count==0 and done.registry_mode=='attached')
assert(done.observed==3 and done.acknowledged==3 and done.birth_confirmed==false and done.delivery_confirmed==false)
assert(ops[1].screen=='X4AuthorityShipRegistry' and ops[1].operation=='Status')
for _,op in ipairs(ops) do assert(not (op.screen=='X4AuthorityShipRegistry' and op.operation=='Initialize')) end
for _,kind in ipairs({'wrong_epoch','wrong_last','uninitialized','faulted','queue_existing','lost_pause','timeout','not_paused','resume_timeout'}) do
 local failed,requests,_,_,reason=scenario(kind)
 assert(failed:state()=='failed' and reason,kind)
 for _,op in ipairs(requests) do assert(not (op.screen=='X4AuthorityShipRegistry' and op.operation=='Initialize'),kind) end
 if kind~='resume_timeout' then
  for _,op in ipairs(requests) do assert(not (op.screen=='X4AuthorityJobShipEvents' and op.operation=='Abort'),kind) end
 end
end
local function invalid(overrides)
 local options={enabled=true,epoch=string.rep('a',32),baseline={},capacity=1,window=1,timeout=1,probe=probe,
  attach_saved_registry=true,exclusive_registry_consumer=true,expected_last=10,can_attach=function() return true end,
  register=function() end,trigger=function() end,convert64=function() end,to_lua_id=function() end,
  valid=function() end,clock=function() end,report=function() end,done=function() end,fault=function() end,can_observe=function() end}
 for key,value in pairs(overrides) do options[key]=value end
 assert(not pcall(host.new,options))
end
invalid({exclusive_registry_consumer=false});invalid({expected_last=-1});invalid({attach_saved_registry='yes'});invalid({baseline={42}})
print('saved registry attach checks passed')
