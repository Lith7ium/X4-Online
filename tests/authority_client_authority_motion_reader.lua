-- Actual local reader + saved bootstrap + source sampler; simulated MD/FFI.
local reader_mod=dofile('src/authority/lua/client_authority_motion_reader.lua')
local bootstrap_mod=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local sampler_mod=dofile('src/authority/lua/source_motion_sampler.lua')
local function rig(mode)
 local now,game,inspects,registrations=1,10,0,0;local granted=true;local output={};local reader
 local epoch,generation=('a'):rep(32),('b'):rep(32);local bnonce,snonce=('c'):rep(32),('d'):rep(32)
 local actor={};local rid,staged_copy,sampler_original
 reader=assert(reader_mod.new({enabled=true,epoch=epoch,generation=generation,index=1318,baseline=10054,sector='cluster_115_sector001_macro',
  bootstrap_nonce=bnonce,sampler_nonce=snonce,guard=function()
   if mode=='guard_mutation' and staged_copy then staged_copy.x=999 end
   if mode=='guard_original_mutation' and staged_copy and sampler_original then sampler_original.x=999 end
   return true
  end,
  authority=function(e,g,i)assert(e==epoch and g==generation and i==1318);return granted end,
  fault=function()end,stage_sample=function(v)
   if mode=='reentrant' then pcall(function()reader:tick()end)end
   assert(v.actor==nil and v.local_sector_key==nil);staged_copy=v
   if mode=='position_mutation' then v.x=999 end
   if mode=='metatable_mutation' then setmetatable(v,{}) end
   if mode=='extra_mutation' then v.extra=true end
   if mode=='rate_mutation' and v.velocity then v.velocity.x=999 end
   output[#output+1]=v;return true
  end,
  bootstrap_factory=function(opt)
   return bootstrap_mod.new({enabled=true,epoch=opt.epoch,baseline=opt.baseline,nonce=opt.nonce,timeout=5,
    clock=function()return now end,guard=function()return true end,baseline_guard=function()return granted end,
    issue=function(_,_,args)rid=args.request_id;return true end,parse=function(v)return v=='0x1' and actor or (v=='0x2' and {} or nil)end,
    inspect=function()inspects=inspects+1;return not (mode=='bootstrap_late_failure' and inspects==2)end,complete=opt.complete})
  end,
  sampler_factory=function(opt)
   local s=assert(sampler_mod.new({enabled=true,epoch=opt.epoch,generation=opt.generation,nonce=opt.nonce,
    clock=function()return now end,guard=function()return true end,binding_guard=function()return false end,
    saved_baseline_limit=opt.saved_baseline_limit,saved_baseline_guard=opt.saved_baseline_guard,
    actor_key=function(a)if a==actor then return '1' end end,fault=opt.fault,max_tracks=1,scan_budget=1,interval=.01,timeout=5,min_dt=.02,max_dt=1,
    reader_factory=function(row,a,request)
     assert(a==actor);return {start=function()rid=request;return true end,tick=function()return true end,response=function()
      return true,{epoch=epoch,index=row.index,sequence=nil,descriptor_atomic=false,sector_identity_proven=false,
       sector_macro='cluster_115_sector001_macro',local_sector_key='2',game_before_pose=game,game_after_pose=game,x=game,y=1,z=2}
     end}
    end}))
   local original=s.register;s.register=function(...)registrations=registrations+1;return original(...)end
   local original_event=s.event;s.event=function(...)local ok,v=original_event(...);sampler_original=v;return ok,v end
   return s
  end}))
 assert(reader:start() and rid==reader:expected_request())
 if mode=='wrong_id' then assert(not reader:event(('9'):rep(32)..'|junk') and registrations==0);return end
 if mode=='grant_revoked' then granted=false;assert(not reader:tick() and registrations==0);return end
 local response=rid..'|'..epoch..'|1318|ok|0x1|ship_macro|owner|0x2|cluster_115_sector001_macro'
 if mode=='bootstrap_late_failure' then assert(not reader:event(response) and registrations==0);return end
 assert(reader:event(response) and registrations==1 and reader:state()=='sampling')
 assert(reader:tick() and rid==reader:expected_request());local accepted=reader:event(rid..'|sample')
 if mode=='reentrant' or mode=='position_mutation' or mode=='metatable_mutation' or mode=='extra_mutation' or mode=='guard_mutation' or mode=='guard_original_mutation' then assert(not accepted and reader:state()=='failed');return end
 assert(accepted)
 assert(#output==1 and output[1].index==1318 and output[1].sequence==1 and output[1].velocity==nil)
 game=10.5;now=1.5;assert(reader:tick());local second=reader:event(rid..'|sample')
 if mode=='rate_mutation' then assert(not second and reader:state()=='failed');return end
 assert(second);assert(#output==2 and output[2].sequence==2 and output[2].velocity.x==1 and output[2].velocity.y==0)
 granted=false;assert(not reader:tick() and #output==2)
end
for _,mode in ipairs({'ok','wrong_id','grant_revoked','bootstrap_late_failure','reentrant','position_mutation','metatable_mutation','extra_mutation','guard_mutation','guard_original_mutation','rate_mutation'})do rig(mode)end
print('local client authority reader tests passed')
