local mod=dofile('src/authority/lua/source_motion_sampler.lua')
local epoch,generation,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32)
local function rig(options)
 options=options or {};local clock=0;local values={};local outputs={};local faults={};local healthy=true
 local x
 x=assert(mod.new({enabled=true,epoch=epoch,generation=generation,nonce=nonce,max_tracks=10,scan_budget=2,
  interval=.1,timeout=2,min_dt=.02,max_dt=1,clock=function()return clock end,
  guard=function()return healthy end,actor_key=function(a)return tostring(a)end,
  binding_guard=function(row,actor)return actor==row.index+40 end,
  reader_factory=function(row,actor,request)
   return {start=function()return true end,tick=function()return true end,
    response=function(_,raw)
     assert(raw==request..'|response')
     local v=table.remove(values,1);assert(v)
     return true,{epoch=epoch,index=row.index,sequence=row.sequence,sector_macro=v[1],
      game_before_pose=v[2],game_after_pose=v[2],x=v[3],y=0,z=0,local_sector_key=v[4] or '43',descriptor_atomic=false,sector_identity_proven=false}
    end}
  end,fault=function(v)faults[#faults+1]=v end}))
 local function register(index)
  return x:register({epoch=epoch,index=index,sequence=index,classification='new_registry_entry'},index+40)
 end
 local function sample(sector,t,pos,local_sector_key)
  values[#values+1]={sector,t,pos,local_sector_key};clock=clock+.2
  assert(x:tick());local req=x:expected_request();assert(req)
  local ok,result=x:event(req..'|response');assert(ok);if result then outputs[#outputs+1]=result end
 end
 return x,register,sample,outputs,faults,function(v)clock=v end,function(v)healthy=v end
end
-- Same actor, finite-difference velocity; changed sector/time gap resets to unknown.
do
 local x,add,sample,out=rig();assert(add(1))
 sample('sector_a',100,10);assert(out[1].sequence==1 and out[1].velocity==nil)
 sample('sector_a',100.5,20);assert(out[2].sequence==2 and out[2].velocity.x==20)
 sample('sector_b',101,20);assert(out[3].velocity==nil)
 sample('sector_b',103,20);assert(out[4].velocity==nil)
 sample('sector_b',103.5,20);assert(out[5].velocity.x==0)
 assert(x:close())
end
-- A zero displacement is a measured zero vector only with two distinct,
-- sufficiently close source-game timestamps in the same local sector.
do
 local x,add,sample,out=rig();assert(add(1))
 sample('sector_a',100,10);assert(out[1].velocity==nil)
 sample('sector_a',100,10);assert(#out==1)
 sample('sector_a',100.01,10);assert(#out==2 and out[2].velocity==nil)
 sample('sector_a',100.5,10)
 local v=out[3].velocity
 assert(out[3].sequence==3 and v and v.x==0 and v.y==0 and v.z==0)
 sample('sector_a',102,10);assert(out[4].velocity==nil)
 assert(x:close())
end
-- Identical source time is suppressed; an actual sector-frame change resets
-- the rate even when it was first observed at the suppressed timestamp.
do
 local x,add,sample,out=rig();assert(add(1))
 sample('sector_a',100,0,'43');sample('sector_a',100,1,'43');assert(#out==1)
 sample('sector_b',100.5,5,'44');assert(#out==2 and out[2].sequence==2 and out[2].velocity==nil)
 sample('sector_c',100.5,8,'45');assert(#out==2)
 sample('sector_c',101,10,'45');assert(#out==3 and out[3].sequence==3 and out[3].velocity==nil)
 sample('sector_c',101.5,12,'45');assert(#out==4 and out[4].velocity.x==4)
end
-- A changed local sector under the same portable macro is ambiguous on the wire.
do
 local x,add,sample=rig();assert(add(1));sample('sector_a',100,0,'43')
 assert(not pcall(sample,'sector_a',100.5,5,'44') and x:state()=='failed')
end
-- A suppressed intermediate frame cannot hide a change of the last sent frame.
do
 local x,add,sample=rig();assert(add(1));sample('sector_a',100,0,'43')
 sample('sector_b',100,0,'44')
 assert(not pcall(sample,'sector_a',100.5,5,'45') and x:state()=='failed')
end
-- Fair bounded traversal and per-index sequence.
do
 local x,add,sample,out=rig();assert(add(1) and add(2))
 sample('sector_a',100,10);sample('sector_b',100.5,20)
 assert(out[1].index==1 and out[2].index==2 and out[1].sequence==1 and out[2].sequence==1)
end
-- Clock/actor loss, foreign response, timeout, duplicate, callback mutation/reentry fence.
do local x,add,sample=rig();assert(add(1));sample('sector_a',100,1);local ok=pcall(sample,'sector_a',99,1);assert(not ok and x:state()=='failed')end
do local x,add=rig();assert(add(1));assert(not add(1) and x:state()=='failed')end
do local x,add=rig();assert(add(1));assert(x:tick());assert(not x:event(string.rep('f',32)..'|response') and x:state()=='failed')end
do local x,add,_,_,_,clock=rig();assert(add(1));assert(x:tick());clock(3);assert(not x:tick() and x:state()=='failed')end
do local x,add,_,_,_,_,health=rig();assert(add(1));health(false);assert(not x:tick() and x:state()=='failed')end
assert(mod.new({enabled=false})==nil)
print('source motion sampler synthetic checks passed')
