local host=dofile('tools/dev/authority_job_registry_host.lua')
local probe=dofile('tools/dev/authority_job_registry_probe.lua')
assert(host.new({enabled=false})==nil)
assert(host.new_x4({enabled=false})==nil)
local function scenario(with_event,kind,expose)
 local handlers,queue,issued,rows={}, {}, {}, {}
 local t,last,observed,ack=.0,0,0,0
 local done,fault
 local raw=42
 local function emit(name,value) queue[#queue+1]={name,value} end
 local opts={enabled=true,expose_actor=expose,epoch=string.rep('a',32),baseline={10},capacity=4,window=1,timeout=.3,probe=probe,
  register=function(name,fn) assert(not handlers[name]);handlers[name]=fn end,
  convert64=function(v) if type(v)=='table' then return v.id end return v end,
  to_lua_id=function(k) if kind=='bad_conversion' then return {id='99'} end return {id=k} end,
  valid=function() return true end,can_observe=function() return kind~='source_stopped' or t<.5 end,clock=function() return t end,
  report=function(...) local row,actor=...;row._test_argc=select('#',...);row._test_actor=actor;rows[#rows+1]=row;return true end,done=function(row) done=row;return true end,
  fault=function(reason) fault=reason end}
 opts.trigger=function(screen,operation,args)
  issued[#issued+1]={screen=screen,operation=operation,args=args}
  if kind=='trigger_false' then return false end
  if kind=='timeout' then return end
  if screen=='X4AuthorityShipRegistry' and operation=='Initialize' then emit(screen..'.Initialized',opts.epoch)
  elseif screen=='X4AuthorityShipRegistry' and operation=='Enroll' then
   assert(type(args.ship)=='table');last=last+1;emit(screen..'.Enrolled',last)
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Initialize' then
   observed=with_event and 1 or 0;emit(screen..'.Initialized',opts.epoch)
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Status' and kind=='overflow' then emit(screen..'.Faulted')
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Status' then
   if kind=='never_drains' then observed=ack+1;raw=42+ack end
   emit(screen..'.Epoch',opts.epoch);emit(screen..'.Observed',observed);emit(screen..'.Acknowledged',ack)
   emit(screen..'.Depth',observed-ack);emit(screen..'.Inflight',0);emit(screen..'.Reason','')
   emit(screen..'.Healthy')
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Front' then
   if observed>ack then emit(screen..'.Sequence',ack+1);emit(screen..'.Actor',raw) else emit(screen..'.Empty') end
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Ack' then
   assert(args.sequence==ack+1 and args.index==ack+2);ack=ack+1;emit(screen..'.Acked',ack)
  elseif screen=='X4AuthorityJobShipEvents' and operation=='Abort' then return
  else error('unexpected request '..screen..'.'..operation) end
 end
 local app=host.new(opts)
 if kind=='trigger_false' then assert(not app:start());return app,issued,rows,done,fault end
 assert(app:start())
 for _=1,30 do
  while #queue>0 do local event=table.remove(queue,1);assert(handlers[event[1]])(nil,event[2]) end
  if app:state()=='done' or app:state()=='failed' then break end
  t=t+.11;app:tick()
 end
 return app,issued,rows,done,fault
end
local app,_,rows,result,err=scenario(true)
assert(app:state()=='done',tostring(err));assert(#rows==1 and rows[1].classification=='new_registry_entry')
assert(rows[1]._test_argc==1 and rows[1]._test_actor==nil)
local exposed,_,exposed_rows=scenario(true,nil,true)
assert(exposed:state()=='done' and exposed_rows[1]._test_argc==2 and exposed_rows[1]._test_actor==42)
assert(result.observed==1 and result.acknowledged==1 and result.birth_confirmed==false and result.delivery_confirmed==false)
local empty,_,_,empty_result=scenario(false)
assert(empty:state()=='done' and empty_result.classification=='inconclusive_no_events')
local invalid,_,_,_,invalid_error=scenario(true,'bad_conversion')
assert(invalid:state()=='failed' and invalid_error)
local timeout,_,_,_,timeout_error=scenario(false,'timeout')
assert(timeout:state()=='failed' and timeout_error)
local overflow,_,_,_,overflow_error=scenario(true,'overflow')
assert(overflow:state()=='failed' and overflow_error)
local stopped,_,_,_,stopped_error=scenario(true,'source_stopped')
assert(stopped:state()=='failed' and stopped_error)
local busy,_,_,_,busy_error=scenario(true,'never_drains')
assert(busy:state()=='failed' and busy_error and busy_error:find('drain timeout',1,true))
local refused,_,_,_,refused_error=scenario(false,'trigger_false')
assert(refused:state()=='failed' and refused_error and refused_error:find('request dispatch failed',1,true))
print('job registry host checks passed')
