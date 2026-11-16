local stream=dofile('src/authority/lua/experimental_saved_motion_stream.lua')
local bind=dofile('src/authority/lua/replica_motion_binding.lua')
local writer=dofile('src/authority/lua/saved_motion_apply.lua')
local E,G,N=('a'):rep(32),('b'):rep(32),('c'):rep(32)
local function rig(mode)
 local now,game=1,10;local binding_id,writer_id;local writes=0;local target_x=0;local faults={};local completed={};local owner
 local o={enabled=true,epoch=E,generation=G,index=1318,sector_macro='cluster_115_sector001_macro',max_samples=3,
  timeout=5,max_age=3,clock=function()return now end,guard=function()return true end,
  fault=function(why,uncertain)faults[#faults+1]={why,uncertain}end,
  complete=function(s)
   completed[#completed+1]=s.sequence
   if mode=='mutate' then s.x=999 end
   if mode=='reentrant' then pcall(function()owner:tick()end) end
   return true
  end}
 o.binding_factory=function(opt)
  return bind.new({enabled=true,epoch=E,generation=G,index=1318,sector_macro=o.sector_macro,nonce=N,
   timeout=5,max_age=3,clock=o.clock,guard=o.guard,capture_binding=opt.capture_binding,complete=opt.complete,
   issue=function(_,_,v)binding_id=v.request_id;return true end,
   inspect=function()return '42','43',true,'44' end})
 end
 o.writer_factory=function(opt)
  local w=assert(writer.new({enabled=true,timeout=5,clock=o.clock,game=function()return game end,guard=opt.guard,fault=opt.fault,
   issue=function(id)writer_id=id;return true end,
   inspect=function()return {x=target_x,y=0,z=0,yaw=0,pitch=0,roll=0}end,
   write=function(_,p)writes=writes+1;target_x=p.x;if mode=='write_error' then error('uncertain')end;return true end,
   log=function()return true end}))
  if mode=='state_reentrant' then
   w.state=function()pcall(function()owner:tick()end);return 'settling' end
  end
  return w
 end
 owner=assert(stream.new(o));assert(owner:start())
 local function sample(i)
  local s={version=1,epoch=E,generation=G,index=1318,sequence=i,sector_macro=o.sector_macro,
   source_time=i,x=i*10,y=0,z=0,digest=('d'):rep(64),request=string.format('%032x',i)}
  if i>1 then s.velocity={x=10,y=0,z=0}end;return s
 end
 local function begin(i)
  assert(owner:submit(sample(i)));assert(owner:binding_event(binding_id..'|Bound|1318|0x2a|0x2b'))
 end
 local function finish()
  assert(owner:writer_event(writer_id..'|ok'));now=now+1.1;game=game+1.1
  assert(owner:tick());assert(owner:writer_event(writer_id..'|ok'))
  return owner:tick()
 end
 if mode=='normal' then
  for i=1,3 do begin(i);assert(finish())end
  assert(owner:state()=='done' and writes==3 and #completed==3 and not owner:outcome_uncertain())
 elseif mode=='write_error' then
  begin(1);assert(not owner:writer_event(writer_id..'|ok'));assert(owner:state()=='failed' and writes==1 and owner:outcome_uncertain())
  assert(not owner:submit(sample(1)) and writes==1)
 elseif mode=='state_reentrant' then
  begin(1);assert(not owner:tick() and owner:state()=='failed' and writes==0 and #completed==0)
 elseif mode=='stale' then
  assert(owner:submit(sample(1)));now=5;assert(not owner:binding_event(binding_id..'|Bound|1318|0x2a|0x2b'))
  assert(writes==0 and owner:state()=='failed')
 elseif mode=='duplicate' then
  begin(1);assert(finish());assert(not owner:submit(sample(1)) and writes==1)
 elseif mode=='actor_changed' then
  begin(1);assert(finish());assert(owner:submit(sample(2)))
  assert(not owner:binding_event(binding_id..'|Bound|1318|0x2c|0x2b') and writes==1 and owner:state()=='failed')
 elseif mode=='old_source_time' then
  begin(1);assert(finish());local s=sample(2);s.source_time=1
  assert(not owner:submit(s) and writes==1)
 elseif mode=='original_mutated' then
  local s=sample(1);assert(owner:submit(s));s.x=999
  assert(owner:binding_event(binding_id..'|Bound|1318|0x2a|0x2b'));assert(finish())
  assert(target_x==10 and completed[1]==1)
 elseif mode=='wrong_identity' then
  local s=sample(1);s.sector_macro='other';assert(not owner:submit(s) and writes==0)
 elseif mode=='mutate' or mode=='reentrant' then
  begin(1);assert(not finish());assert(owner:state()=='failed' and writes==1 and owner:outcome_uncertain())
 end
end
for _,mode in ipairs({'normal','write_error','state_reentrant','stale','duplicate','actor_changed','old_source_time','original_mutated','wrong_identity','mutate','reentrant'})do rig(mode)end
assert(stream.new({})==nil)
print('bounded offline saved motion stream passed')
