local M=dofile('src/authority/lua/job_delivery.lua')
assert(M.new({enabled=false})==nil)
local epoch=string.rep('a',32)
local generation=string.rep('d',32)
local peers={{id='alice',incarnation=string.rep('1',32)},{id='bob',incarnation=string.rep('2',32)},{id='carol',incarnation=string.rep('3',32)}}
local function event()return {epoch=epoch,generation=generation,sequence=1,index=10055,descriptor={macro='ship_macro',faction='pioneers',sector_macro='sector_macro',x=1,y=2,z=3}}end
local function copy(t)if type(t)~='table'then return t end;local r={};for k,v in pairs(t)do r[k]=copy(v)end;return r end
local function setup(opts)
 opts=opts or {};local t=0;local members=copy(peers);local sent,released={},{}
 local c
 c=M.new({enabled=true,generation=opts.generation or generation,timeout=2,clock=function()return t end,
  membership=function()if opts.membership then return opts.membership(c,members) end;return members end,
  send=function(peer,e)sent[#sent+1]={peer=peer,event=e};if opts.send then return opts.send(c,peer,e) end;return true end,
  release=function(a,b,d)released[#released+1]={a,b,d};if opts.release then return opts.release(c) end;return true end})
 return c,sent,released,function(v)t=v end,members
end
-- Distinct clients acknowledge out of order; duplicates are harmless and do not release early.
local c,sent,released,_,members=setup();local e=event()
assert(c:begin(e) and #sent==3 and #released==0)
e.descriptor.x=999 -- Caller mutations do not rewrite the frozen event.
assert(c:ack(members[2],sent[2].event));assert(c:ack(members[2],sent[2].event));assert(#released==0)
assert(c:ack(members[3],sent[3].event));assert(#released==0)
assert(c:ack(members[1],sent[1].event));assert(#released==1 and c:state()=='released')
assert(c:ack(members[1],sent[1].event));assert(#released==1)
assert(c:source_acked(epoch,1,10055) and c:state()=='idle')
local next_event=event();next_event.sequence=2;assert(c:begin(next_event))
-- Two connected clients likewise require two distinct confirmations.
do
 local q,s,r,_,m=setup();table.remove(m,3);assert(q:begin(event()));assert(q:ack(m[1],s[1].event))
 assert(#r==0);assert(q:ack(m[2],s[2].event));assert(#r==1)
end
-- Wrong correlation, descriptor, participant, incarnation and actor-handle fields never release.
local cases={
 function(p,e)p.id='intruder'end,
 function(p,e)p.incarnation=string.rep('f',32)end,
 function(p,e)e.epoch=string.rep('b',32)end,
 function(p,e)e.generation=string.rep('f',32)end,
 function(p,e)e.sequence=2 end,
 function(p,e)e.index=5 end,
 function(p,e)e.descriptor.x=5 end,
 function(p,e)e.descriptor.sector_macro='other'end,
 function(p,e)e.descriptor.actor='1234'end,
 function(p,e)e.actor='1234'end,
}
for _,mutate in ipairs(cases)do
 local q,s,r,_,m=setup();assert(q:begin(event()));local p,e2=copy(m[1]),copy(s[1].event);mutate(p,e2)
 assert(not q:ack(p,e2) and q:state()=='failed' and #r==0)
end
-- A new queue incarnation cannot consume a buffered ACK from an old one,
-- even with identical epoch, sequence, index, descriptor and connection.
do
 local old,oldsent=setup();assert(old:begin(event()))
 local fresh_generation=string.rep('e',32)
 local fresh,s,r,_,m=setup({generation=fresh_generation});local next_event=event();next_event.generation=fresh_generation
 assert(fresh:begin(next_event));assert(not fresh:ack(m[1],oldsent[1].event));assert(#r==0 and fresh:state()=='failed')
end
-- Missing, disconnected, replaced or new members fence the active event.
for _,change in ipairs({function(m)table.remove(m,1)end,function(m)m[1].incarnation=string.rep('f',32)end,
 function(m)m[#m+1]={id='dave',incarnation=string.rep('4',32)}end,function(m)m[2].id=m[1].id end})do
 local q,s,r,_,m=setup();assert(q:begin(event()));change(m);assert(not q:ack(peers[1],s[1].event) and #r==0)
end
-- No membership and malformed descriptors are refused before any send.
for _,bad in ipairs({{},{{id='alice',incarnation='bad'}},
 {{id='alice',incarnation=string.rep('1',32)},{id='bob',incarnation=string.rep('1',32)}}})do
 local q,s,r=setup({membership=function()return bad end});assert(not q:begin(event()) and #s==0 and #r==0)
end
do local q,s,r=setup();local x=event();x.descriptor.x=0/0;assert(not q:begin(x) and #s==0 and #r==0)end
do local q,s,r=setup();local x=event();x.generation=string.rep('e',32);assert(not q:begin(x) and #s==0 and #r==0)end
do
 local ok=pcall(M.new,{enabled=true,timeout=1,clock=function()return 0 end,membership=function()return peers end,
  send=function()return true end,release=function()return true end})
 assert(not ok)
end
-- Timeout and clock regression fence without a release.
do local q,s,r,set=setup();assert(q:begin(event()));set(2);assert(not q:tick() and #r==0)end
do local q,s,r,set=setup();assert(q:begin(event()));set(-1);assert(not q:tick() and #r==0)end
-- Dispatch failure, a synchronous/reentrant ACK, or release failure fences.
do local q,s,r=setup({send=function()return false end});assert(not q:begin(event()) and #r==0)end
do local q,s,r=setup({send=function(self,p,e)self:ack(p,e);return true end});assert(not q:begin(event()) and q:state()=='failed' and #r==0)end
do local q,s,r,_,m=setup({release=function()return false end});assert(q:begin(event()));assert(q:ack(m[1],s[1].event));assert(q:ack(m[2],s[2].event));assert(not q:ack(m[3],s[3].event) and #r==1 and q:state()=='failed')end
-- Source receipt is separately correlated; no subsequent event before it.
do local q,s,r,_,m=setup();assert(q:begin(event()));for i=1,3 do assert(q:ack(m[i],s[i].event))end;assert(not q:source_acked(epoch,2,10055) and q:state()=='failed')end
do local q,s,r,_,m=setup();assert(q:begin(event()));for i=1,3 do assert(q:ack(m[i],s[i].event))end;assert(not q:begin(event()) and q:state()=='failed')end
print('job delivery offline checks passed')
