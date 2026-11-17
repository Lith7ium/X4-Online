-- Existing bootstrap and sampler with synthetic player-control checks.
local Reader=dofile('src/authority/lua/client_authority_motion_reader.lua')
local Bootstrap=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local Sampler=dofile('src/authority/lua/source_motion_sampler.lua')
local epoch,generation=('a'):rep(32),('b'):rep(32)
local function run(slot,mode)
 local index,sector=slot+2,'cluster_01_sector001_macro'
 local actor,other={},{};local now,game=1,10;local controlled=actor;local rid,staged,staged_count=nil,nil,0
 local sector_key='2'
 local reader=assert(Reader.new({enabled=true,epoch=epoch,generation=generation,index=index,baseline=4,
  fixture_slot=slot,sector=sector,include_orientation=true,latest_cache=mode=='cache_sector_changed',
  current_sector=function()return sector_key,sector end,bootstrap_nonce=('c'):rep(32),sampler_nonce=('d'):rep(32),
  guard=function() return true end,authority=function(e,g,i) return e==epoch and g==generation and i==index end,
  controlled=function(value)return value==controlled end,fault=function()end,
  stage_sample=function(value)
   assert(value.actor==nil and value.local_sector_key==nil and value.index==index and value.version==2)
   staged=value;staged_count=staged_count+1
   if mode=='loss_after_stage' then controlled=other end
   return true
  end,
  bootstrap_factory=function(options)
   return Bootstrap.new({enabled=true,epoch=epoch,baseline=4,nonce=options.nonce,timeout=5,
    clock=function()return now end,guard=function()return true end,baseline_guard=function()return true end,
    issue=function(_,_,args)rid=args.request_id;return true end,
    parse=function(value)return value=='0x1' and actor or (value=='0x2' and other or nil)end,
    inspect=function()return true end,complete=options.complete})
  end,
  sampler_factory=function(options)
   return Sampler.new({enabled=true,epoch=epoch,generation=generation,nonce=options.nonce,include_orientation=true,
    clock=function()return now end,guard=function()return true end,binding_guard=function()return false end,
    saved_baseline_limit=4,saved_baseline_guard=options.saved_baseline_guard,actor_key=function(value)return value==actor and '1' or nil end,
    fault=options.fault,max_tracks=1,scan_budget=1,interval=.01,timeout=5,min_dt=.02,max_dt=1,
    reader_factory=function(row,value,request)
     assert(value==actor);return {start=function()rid=request;return true end,tick=function()return true end,response=function()
      if mode=='loss_during_read' then controlled=other end
      return true,{epoch=epoch,index=row.index,descriptor_atomic=false,sector_identity_proven=false,
       sector_macro=sector,local_sector_key='2',game_before_pose=game,game_after_pose=game,
       x=game,y=1,z=2,yaw=.1,pitch=.2,roll=.3}
     end}
    end})
  end}))
 assert(reader:start())
 if mode=='wrong_control_at_bootstrap' then controlled=other end
 local accepted=reader:event(rid..'|'..epoch..'|'..index..'|ok|0x1|ship_macro|player|0x2|'..sector)
 if mode=='wrong_control_at_bootstrap' then assert(not accepted and reader:state()=='failed' and staged_count==0);return end
 assert(accepted and reader:state()=='sampling')
 if mode=='cache_sector_changed' then
  assert(reader:cache_context());sector_key='3';assert(reader:cache_context()==nil and reader:state()=='failed');return
 end
 if mode=='loss_before_read' then controlled=other;assert(not reader:tick() and staged_count==0);return end
 assert(reader:tick());accepted=reader:event(rid..'|sample')
 if mode=='loss_during_read' then assert(not accepted and staged_count==0);return end
 if mode=='loss_after_stage' then assert(not accepted and staged_count==1);return end
 assert(accepted and staged_count==1 and staged.index==index and staged.orientation.yaw==.1)
 game=10.5;now=1.5;assert(reader:tick());assert(reader:event(rid..'|sample'))
 assert(staged_count==2 and staged.velocity.x==1 and staged.angular_rate.yaw==0)
end
for _,slot in ipairs({1,2}) do
 for _,mode in ipairs({'normal','wrong_control_at_bootstrap','loss_before_read','loss_during_read','loss_after_stage','cache_sector_changed'}) do
  run(slot,mode)
 end
end
local base={enabled=true,epoch=epoch,generation=generation,bootstrap_nonce=('c'):rep(32),sampler_nonce=('d'):rep(32),
 guard=function()return true end,authority=function()return true end,bootstrap_factory=function()end,
 sampler_factory=function()end,stage_sample=function()end,fault=function()end,controlled=function()return true end}
for _,bad in ipairs({{slot=1,index=4,baseline=4,orientation=true},{slot=2,index=4,baseline=10054,orientation=true},
 {slot=1,index=3,baseline=4,orientation=false},{slot=3,index=5,baseline=4,orientation=true}})do
 local options={};for key,value in pairs(base)do options[key]=value end
 options.fixture_slot=bad.slot;options.index=bad.index;options.baseline=bad.baseline
 options.include_orientation=bad.orientation;options.sector='sector_a'
 assert(not pcall(Reader.new,options))
end
print('fixture player authority reader checks passed')
