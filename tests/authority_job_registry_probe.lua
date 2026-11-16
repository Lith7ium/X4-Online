local M=dofile('tools/dev/authority_job_registry_probe.lua')
assert(M.new({enabled=false})==nil)
do
 local ok=pcall(M.new,{enabled=true,epoch=string.rep('a',32),last=0,baseline={},expose_actor='true',
  issue=function() end,key=function() end,to_md_actor=function() end,valid=function() end,report=function() end})
 assert(not ok)
end
local function setup(convert, issue_result, report_result)
 local issued,rows={},{}
 local alive=true
 local p=M.new({enabled=true,epoch=string.rep('a',32),last=3,baseline={old=2},
  issue=function(screen,op,args) issued[#issued+1]={screen=screen,op=op,args=args};return issue_result~=false end,
  key=function(actor) return type(actor)=='table' and actor.id or actor end,
  to_md_actor=convert or function(actor) return {id=actor} end,valid=function() return alive end,
  report=function(row) rows[#rows+1]=row;return report_result~=false end})
 return p,issued,rows,function(v) alive=v end
end
local function item(p,seq,actor,index)
 assert(p:front());assert(p:event('Sequence',seq));assert(p:event('Actor',actor))
 assert(p:event('Enrolled',index));assert(p:event('Acked',seq))
end
local p,issued,rows=setup()
item(p,1,'old',2);item(p,2,'previously_missing',1);item(p,3,'new',4);item(p,4,'new',4)
assert(type(issued[2].args.ship)=='table' and issued[2].args.ship.id=='old')
assert(rows[1].classification=='previously_observed')
assert(rows[2].classification=='previously_unobserved_existing_index')
assert(rows[3].classification=='new_registry_entry')
assert(rows[4].classification=='previously_observed')
for _,row in ipairs(rows) do assert(row.birth_confirmed==false and row.delivery_confirmed==false) end
assert(p:front());assert(p:event('Empty'));assert(p:state()=='idle')
local collision,ops=setup()
assert(collision:front());assert(collision:event('Sequence',1));assert(collision:event('Actor','other'))
assert(not collision:event('Enrolled',2));assert(collision:state()=='failed');assert(ops[#ops].op=='Abort')
local dead,requests,_,alive=setup()
assert(dead:front());assert(dead:event('Sequence',1));assert(dead:event('Actor','old'))
alive(false);assert(not dead:event('Enrolled',2));assert(requests[#requests].op=='Abort')
local overflow,overflow_ops=setup()
assert(overflow:front());assert(not overflow:event('Faulted'));assert(overflow_ops[#overflow_ops].op=='Abort')
local lost=setup();assert(lost:front());assert(not lost:timeout());assert(not lost:event('Sequence',1))
local gap=setup();assert(gap:front());assert(not gap:event('Sequence',2))
local duplicate=setup();item(duplicate,1,'old',2);assert(duplicate:front());assert(not duplicate:event('Sequence',1))
for _,convert in ipairs({function() return nil end,function() return {id='different'} end,function() error('bad conversion') end}) do
 local bad,ops=setup(convert);assert(bad:front());assert(bad:event('Sequence',1))
 assert(not bad:event('Actor','old'));assert(bad:state()=='failed');assert(#ops==2 and ops[2].op=='Abort')
end
local no_send,send_ops=setup(nil,false);assert(not no_send:front());assert(no_send:state()=='failed');assert(send_ops[#send_ops].op=='Abort')
local no_report,report_ops=setup(nil,nil,false);assert(no_report:front());assert(no_report:event('Sequence',1))
assert(no_report:event('Actor','old'));assert(no_report:event('Enrolled',2))
assert(not no_report:event('Acked',1));assert(no_report:state()=='failed');assert(report_ops[#report_ops].op=='Abort')
-- Deferred delivery reports before source queue ACK. Only the exact pending
-- tuple can release it; no callback can reenter to release during reporting.
local function deferred(mode)
 local ops,rows={},{};local p
 p=M.new({enabled=true,epoch=string.rep('a',32),last=0,baseline={},defer_ack=true,
  issue=function(screen,op,args) ops[#ops+1]={op=op,args=args};return true end,
  key=function(v) return type(v)=='table' and v.id or v end,
  to_md_actor=function(v) return {id=v} end,valid=function() return true end,
  report=function(row) rows[#rows+1]=row;if mode=='reenter' then p:confirm_delivery(row.epoch,row.sequence,row.index) end;return true end})
 assert(p:front());assert(p:event('Sequence',1));assert(p:event('Actor','one'))
 return p,ops,rows
end
do
 local p,ops,rows=deferred();assert(p:event('Enrolled',1));assert(p:state()=='await_delivery')
 assert(#rows==1 and #ops==2 and rows[1].delivery_confirmed==false)
 assert(p:confirm_delivery(string.rep('a',32),1,1));assert(ops[3].op=='Ack')
 assert(p:event('Acked',1));assert(p:state()=='idle' and #rows==1)
 assert(p:front());assert(p:event('Sequence',2));assert(p:event('Actor','two'));assert(p:event('Enrolled',2))
 assert(not p:confirm_delivery(string.rep('a',32),1,1));assert(ops[#ops].op=='Abort')
end
for _,mode in ipairs({'wrong_epoch','wrong_index','duplicate','timeout','reenter'}) do
 local p,ops,rows=deferred(mode)
 if mode=='reenter' then assert(not p:event('Enrolled',1))
 else
  assert(p:event('Enrolled',1))
  if mode=='timeout' then assert(not p:timeout())
  elseif mode=='wrong_epoch' then assert(not p:confirm_delivery(string.rep('b',32),1,1))
  elseif mode=='wrong_index' then assert(not p:confirm_delivery(string.rep('a',32),1,2))
  else assert(p:confirm_delivery(string.rep('a',32),1,1));assert(not p:confirm_delivery(string.rep('a',32),1,1)) end
 end
 assert(p:state()=='failed' and ops[#ops].op=='Abort')
end
-- A callback may reenter and fail the driver while still returning a matching
-- actor value. Never overwrite that failure with an ACK transition.
for _,which in ipairs({'key','valid','issue'}) do
 local p,ops,armed=nil,{},false
 p=M.new({enabled=true,epoch=string.rep('a',32),last=0,baseline={},defer_ack=true,
  issue=function(_,op) ops[#ops+1]=op;if armed and which=='issue' and op=='Ack' then p:timeout() end;return true end,
  key=function(v) if armed and which=='key' then p:timeout() end;return type(v)=='table' and v.id or v end,
  valid=function() if armed and which=='valid' then p:timeout() end;return true end,
  to_md_actor=function(v)return {id=v} end,report=function()return true end})
 assert(p:front());assert(p:event('Sequence',1));assert(p:event('Actor','one'));assert(p:event('Enrolled',1))
 armed=true;assert(not p:confirm_delivery(string.rep('a',32),1,1));assert(p:state()=='failed')
 if which~='issue' then for _,op in ipairs(ops) do assert(op~='Ack') end end
end
for _,event in ipairs({'Enrolled','Acked'}) do
 local p,ops,armed=nil,{},false
 p=M.new({enabled=true,epoch=string.rep('a',32),last=0,baseline={},defer_ack=true,
  issue=function(_,op)ops[#ops+1]=op;return true end,
  key=function(v)if armed then p:timeout() end;return type(v)=='table' and v.id or v end,
  valid=function()return true end,to_md_actor=function(v)return {id=v} end,report=function()return true end})
 assert(p:front());assert(p:event('Sequence',1));assert(p:event('Actor','one'))
 if event=='Acked' then assert(p:event('Enrolled',1));assert(p:confirm_delivery(string.rep('a',32),1,1)) end
 armed=true;assert(not p:event(event,1));assert(p:state()=='failed' and ops[#ops]=='Abort')
end
for _,which in ipairs({'key','convert'}) do
 local p,ops=nil,{}
 p=M.new({enabled=true,epoch=string.rep('a',32),last=0,baseline={},defer_ack=true,
  issue=function(_,op)ops[#ops+1]=op;return true end,
  key=function(v)if which=='key' then p:timeout() end;return type(v)=='table' and v.id or v end,
  valid=function()return true end,to_md_actor=function(v)if which=='convert' then p:timeout() end;return {id=v} end,
  report=function()return true end})
 assert(p:front());assert(p:event('Sequence',1));assert(not p:event('Actor','one'))
 assert(p:state()=='failed');for _,op in ipairs(ops) do assert(op~='Enroll' and op~='Ack') end
end
do
 local p,ops=nil,{}
 p=M.new({enabled=true,epoch=string.rep('a',32),last=0,baseline={},
  issue=function(_,op)ops[#ops+1]=op;return true end,
  key=function(v)return type(v)=='table' and v.id or v end,
  valid=function()return true end,to_md_actor=function(v)return {id=v} end,
  report=function()p:timeout();return true end})
 assert(p:front());assert(p:event('Sequence',1));assert(p:event('Actor','one'));assert(p:event('Enrolled',1))
 assert(not p:event('Acked',1));assert(p:state()=='failed' and ops[#ops]=='Abort')
end
local late,late_ops=setup();assert(late:front());assert(late:event('Sequence',1));assert(late:event('Actor','old'))
assert(late:event('Enrolled',2));assert(not late:event('Enrolled',2));assert(late_ops[#late_ops].op=='Abort')
-- At the exact Lua integer limit no Enroll may be dispatched, including a
-- reactivation already present in the known map. Abort is best effort only.
for _,actor in ipairs({'known','unknown'}) do
 local ops={}
 local bounded=M.new({enabled=true,epoch=string.rep('a',32),last=9007199254740991,
  baseline={known=9007199254740991},issue=function(screen,op,args) ops[#ops+1]={screen=screen,op=op};return true end,
  key=function(v) return type(v)=='table' and v.id or v end,to_md_actor=function(v) return {id=v} end,
  valid=function() return true end,report=function() error('must not report') end})
 assert(bounded:front());assert(bounded:event('Sequence',1))
 local ok,reason=bounded:event('Actor',actor)
 assert(not ok and reason=='index_capacity' and bounded:state()=='failed')
 assert(#ops==2 and ops[1].op=='Front' and ops[2].op=='Abort')
 for _,op in ipairs(ops) do assert(op.op~='Enroll') end
end
-- The same fence applies after the last valid allocation within this run.
local edge_ops={}
local edge=M.new({enabled=true,epoch=string.rep('a',32),last=9007199254740990,baseline={},
 issue=function(screen,op,args) edge_ops[#edge_ops+1]={op=op};return true end,
 key=function(v) return type(v)=='table' and v.id or v end,to_md_actor=function(v) return {id=v} end,
 valid=function() return true end,report=function() return true end})
item(edge,1,'new',9007199254740991)
assert(edge:front());assert(edge:event('Sequence',2))
local ok,reason=edge:event('Actor','new');assert(not ok and reason=='index_capacity')
local enrolls=0;for _,entry in ipairs(edge_ops) do if entry.op=='Enroll' then enrolls=enrolls+1 end end
assert(enrolls==1 and edge_ops[#edge_ops].op=='Abort')
print('job registry diagnostic checks passed')
