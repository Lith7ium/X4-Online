local M=dofile('tools/dev/authority_multi_create_client.lua')
assert(M.new({enabled=false})==nil)
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local function desc(i,sector)return {index=i,macro='ship_arg',sector=sector or 'sector_a',owner='argon',seed=7183,x=1,y=2,z=3,witness_index=1}end
local function rig(mode,baseline)
 local t,guard=1,true;local sent,done,audits={},{},{};local client
 local opts={enabled=true,epoch=epoch,nonce=nonce,baseline=baseline or 2,timeout=5,
  clock=function()return t end,guard=function()return guard end,
  issue=function(screen,op,args)
   sent[#sent+1]={screen=screen,op=op,args=args}
   if mode=='reentrant_issue' then client:event('x') end
   return mode~='dispatch_false'
  end,
  inspect=function(actor,sector,index,d)
   if mode=='reentrant_inspect' then client:close() end
   if mode=='slow_inspect' then t=t+6 end
   if mode=='bad_binding' then return '41',false end
   if mode=='bad_actor' then return '42',true end
   if mode=='mutated_inspect' then d.witness_index=2 end
   if mode=='lost_guard' then guard=false end
   assert(type(d)=='table' and d.index==index and sector=='0x2b')
   return ({['0x29']='41',['0x2a']='42',['0x2d']='45',['0xffffffffffffffff']='18446744073709551615'})[actor],true
  end,
  complete=function(op,result)
   done[#done+1]={op=op,result=result}
   if mode=='mutated_initialize' and op=='initialize' then result.epoch=string.rep('f',32) end
   if mode=='mutated_completion' and op~='initialize' then result.index=99 end
   return true
  end}
 if mode and mode:match('^audit') then
  opts.witness_audit=function(index,sector,witness,eligible)
   audits[#audits+1]={index,sector,witness,eligible}
   if mode=='audit_reentrant' then client:close() end
   if mode=='audit_slow' then t=t+6 end
   if mode=='audit_error' then error('injected audit failure') end
   return mode~='audit_false'
  end
 end
 client=assert(M.new(opts))
 return client,sent,done,function(v)t=v end,audits
end
local function init(c,q)
 assert(c:initialize());local r=q[#q];assert(r.op=='Initialize' and r.args.request_id==nonce..'-1' and r.args.baseline>=2)
 assert(c:event(r.args.request_id..'|Initialized|'..epoch));assert(c:state()=='ready')
end
local function created(c,q,d,actor)
 assert(c:create(d));local r=q[#q];assert(r.op=='Create')
 assert(c:event(r.args.request_id..'|Created|'..d.index..'|'..actor));local i=q[#q]
 assert(i.op=='Inspect' and i.args.index==d.index and i.args.request_id~=r.args.request_id)
 return i
end
local function inspected(c,i,actor)
 return c:event(i.args.request_id..'|Inspected|'..i.args.index..'|'..actor..'|0x2b')
end
do
 local c,q,done=rig();init(c,q)
 local i=created(c,q,desc(3),'0x29');assert(inspected(c,i,'0x29'))
 local j=created(c,q,desc(4,'sector_b'),'0x2a');assert(inspected(c,j,'0x2a'))
 local k=created(c,q,desc(5,'other_saved_sector'),'0x2d');assert(inspected(c,k,'0x2d'))
 local alternate=desc(3);alternate.witness_index=2
 local replay=created(c,q,alternate,'0x29');assert(inspected(c,replay,'0x29'))
 assert(#done==5 and done[2].op=='create' and done[3].op=='create' and done[4].op=='create' and done[5].op=='replay')
 local altered=desc(3);altered.x=4;assert(not c:create(altered) and c:state()=='failed')
end
for _,mode in ipairs({'bad_binding','bad_actor','mutated_inspect','mutated_completion','lost_guard','slow_inspect','reentrant_inspect'})do
 local c,q,done=rig(mode);init(c,q);local i=created(c,q,desc(3),'0x29')
 assert(not inspected(c,i,'0x29') and c:state()=='failed',mode);assert(#done==(mode=='mutated_completion' and 2 or 1))
end
do
 local c,q=rig('mutated_initialize');assert(c:initialize())
 assert(not c:event(q[#q].args.request_id..'|Initialized|'..epoch) and c:state()=='failed')
end
do local c,q,done=rig();init(c,q);assert(not c:create(desc(4)) and #done==1)end
do
 local c,q,done=rig();init(c,q);local i=created(c,q,desc(3),'0xffffffffffffffff')
 assert(inspected(c,i,'0xffffffffffffffff') and done[2].result.actor_key=='18446744073709551615')
end
do
 local c,q,done=rig();init(c,q);assert(c:create(desc(3)));local r=q[#q]
 assert(not c:event(r.args.request_id..'|Created|3|0x10000000000000000') and #done==1)
end
do local c,q,done=rig();init(c,q);local d=desc(3);d.witness_index=3;assert(not c:create(d) and #done==1)end
do
 local c,q,done=rig();init(c,q);local i=created(c,q,desc(3),'0x29')
 assert(not c:event(nonce..'-2|Created|3|0x29'));assert(c:state()=='failed' and #done==1)
end
do
 local c,q,done=rig();init(c,q);local i=created(c,q,desc(3),'0x29')
 assert(not inspected(c,i,'0x2a'));assert(c:state()=='failed' and #done==1)
end
do
 local c,q,done=rig();init(c,q);local i=created(c,q,desc(3),'0x29');assert(inspected(c,i,'0x29'))
 local j=created(c,q,desc(4),'0x29');assert(not inspected(c,j,'0x29') and c:state()=='failed')
end
do local c,q,done,set=rig();init(c,q);assert(c:create(desc(3)));set(10);assert(not c:tick() and #done==1)end
do local c=rig('reentrant_issue');assert(not c:initialize() and c:state()=='failed')end
do local c=rig('dispatch_false');assert(not c:initialize() and c:state()=='failed')end
for _,phase in ipairs({'create_replay','create_pending_clear','create_registry','create_ship','create_pending_set','create_input','create_witness','create_index','create_state'}) do
 local c,q,done=rig();init(c,q);assert(c:create(desc(3)));local id=q[#q].args.request_id
 local ok,reason=c:event(id..'|Refused|'..phase)
 assert(not ok and reason=='refused_'..phase and #done==1 and c:state()=='failed')
end
for _,phase in ipairs({'inspect_binding','inspect_witness','inspect_descriptor'}) do
 local c,q,done=rig();init(c,q);local i=created(c,q,desc(3),'0x29')
 local ok,reason=c:event(i.args.request_id..'|Refused|'..phase)
 assert(not ok and reason=='refused_'..phase and #done==1 and c:state()=='failed')
end
for _,phase in ipairs({'inspect_binding','secret/path','unknown'}) do
 local c,q,done=rig();init(c,q);assert(c:create(desc(3)));local id=q[#q].args.request_id
 local ok,reason=c:event(id..'|Refused|'..phase)
 assert(not ok and reason=='refused_unknown' and #done==1)
end
do
 local c,q,done=rig();init(c,q);assert(c:create(desc(3)))
 local ok,reason=c:event(nonce..'-1|Refused|create_witness')
 assert(not ok and reason=='correlation' and #done==1)
end
do
 local c,q,done=rig();init(c,q);assert(c:create(desc(3)))
 local ok,reason=c:event(q[#q].args.request_id..'|Refused|')
 assert(not ok and reason=='refused' and #done==1)
end
-- Multi-witness search never mutates the game until a matching probe response.
do
 local c,q,done=rig();init(c,q);local candidates={1,2};assert(c:create(desc(3),candidates))
 local a=q[#q];assert(a.op=='Witness' and a.args.witness_index==1)
 candidates[2]=1 -- caller mutation cannot change the frozen pending candidates
 assert(c:event(a.args.request_id..'|Witness|1|0'))
 local b=q[#q];assert(b.op=='Witness' and b.args.witness_index==2 and a.args.request_id~=b.args.request_id)
 assert(c:event(b.args.request_id..'|Witness|2|1'))
 local create=q[#q];assert(create.op=='Create' and create.args.witness_index==2 and #done==1)
 assert(c:event(create.args.request_id..'|Created|3|0x29'))
 local inspect=q[#q];assert(inspect.op=='Inspect' and inspect.args.witness_index==2)
 assert(inspected(c,inspect,'0x29') and #done==2)
end
for _,list in ipairs({{}, {1,1}, {1,3}, {[1]=1,[3]=2}, {2,1}})do
 local c,q,done=rig();init(c,q)
 if list[1]==2 and list[2]==1 then -- valid ordering: any non-duplicate order is allowed
  assert(c:create(desc(3),list)==false) -- descriptor must identify the first candidate
 else assert(not c:create(desc(3),list)) end
 assert(#q==1 and #done==1 and c:state()=='failed')
end
do
 local c,q,done=rig();init(c,q);assert(c:create(desc(3),{1,2}))
 local a=q[#q];assert(c:event(a.args.request_id..'|Witness|1|0'))
 local b=q[#q];local ok,why=c:event(b.args.request_id..'|Witness|2|0')
 assert(not ok and why=='no_witness' and #q==3 and #done==1)
end
for _,response in ipairs({'Witness|2|1','Witness|1|2','Witness|01|1','Witness|1|1|extra','Created|3|0x29'})do
 local c,q,done=rig();init(c,q);assert(c:create(desc(3),{1,2}));local a=q[#q]
 assert(not c:event(a.args.request_id..'|'..response) and #q==2 and #done==1)
end
do
 local c,q,done=rig();init(c,q);assert(c:create(desc(3),{1,2}));local a=q[#q]
 assert(not c:event(nonce..'-1|Witness|1|1') and #done==1 and #q==2)
end
do
 local c,q,done,set=rig();init(c,q);assert(c:create(desc(3),{1,2}));set(5)
 local a=q[#q];assert(c:event(a.args.request_id..'|Witness|1|0'));set(6)
 assert(not c:tick() and c:state()=='failed' and #q==3 and #done==1)
end
do
 local c,q,done=rig();init(c,q);assert(c:create(desc(3),{1,2}));local a=q[#q]
 local ok,why=c:event(a.args.request_id..'|Refused|witness_state')
 assert(not ok and why=='refused_witness_state' and #q==2 and #done==1)
end
do
 local c,q,done=rig(nil,300);init(c,q);local candidates={}
 for i=1,260 do candidates[i]=i end
 assert(c:create(desc(301),candidates))
 for i=1,260 do
  local r=q[#q];assert(r.op=='Witness' and r.args.witness_index==i)
  assert(c:event(r.args.request_id..'|Witness|'..i..'|'..(i==260 and '1' or '0')))
 end
 assert(q[#q].op=='Create' and q[#q].args.witness_index==260 and #done==1)
end
do
 local c,q,done,_,audits=rig('audit');init(c,q);assert(c:create(desc(3),{1,2}))
 local a=q[#q];assert(c:event(a.args.request_id..'|Witness|1|0'))
 local b=q[#q];assert(c:event(b.args.request_id..'|Witness|2|1'))
 assert(#audits==2 and audits[1][1]==3 and audits[1][2]=='sector_a' and audits[1][3]==1 and audits[1][4]==false)
 assert(audits[2][1]==3 and audits[2][2]=='sector_a' and audits[2][3]==2 and audits[2][4]==true)
 assert(q[#q].op=='Create' and #done==1)
end
for _,mode in ipairs({'audit_reentrant','audit_slow','audit_error','audit_false'})do
 local c,q,done,_,audits=rig(mode);init(c,q);assert(c:create(desc(3),{1,2}))
 local a=q[#q];assert(not c:event(a.args.request_id..'|Witness|1|1'))
 assert(c:state()=='failed' and #audits==1 and #q==2 and #done==1)
end
do
 local c,q,done,_,audits=rig('audit');init(c,q);assert(c:create(desc(3),{1,2}));local a=q[#q]
 assert(not c:event(a.args.request_id..'|Witness|2|1') and #audits==0 and #done==1 and #q==2)
end
print('multi-create client synthetic checks passed')
