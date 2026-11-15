local M=dofile('tools/dev/authority_job_registry_probe.lua')
assert(M.new({enabled=false})==nil)
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
local late,late_ops=setup();assert(late:front());assert(late:event('Sequence',1));assert(late:event('Actor','old'))
assert(late:event('Enrolled',2));assert(not late:event('Enrolled',2));assert(late_ops[#late_ops].op=='Abort')
print('job registry diagnostic checks passed')
