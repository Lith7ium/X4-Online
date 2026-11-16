local M=dofile('tools/dev/authority_multi_create_client.lua')
assert(M.new({enabled=false})==nil)
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local function desc(i,sector)return {index=i,macro='ship_arg',sector=sector or 'sector_a',owner='argon',seed=7183,x=1,y=2,z=3,witness_index=1}end
local function rig(mode)
 local t,guard=1,true;local sent,done={},{};local client
 local opts={enabled=true,epoch=epoch,nonce=nonce,baseline=2,timeout=5,
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
 client=assert(M.new(opts))
 return client,sent,done,function(v)t=v end
end
local function init(c,q)
 assert(c:initialize());local r=q[#q];assert(r.op=='Initialize' and r.args.request_id==nonce..'-1' and r.args.baseline==2)
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
print('multi-create client synthetic checks passed')
