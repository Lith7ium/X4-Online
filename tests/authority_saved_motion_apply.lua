local writer_module=dofile('src/authority/lua/saved_motion_apply.lua')
local owner_module=dofile('src/authority/lua/motion_client_owner.lua')
local function rig(mode)
 local now,game=1,10;local callbacks,input,out,logs,faults={}, {}, {}, {}, {}; local writes=0;local guard_ok=true;local healthy=true
 local lease,attempt,epoch,generation,nonce=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32),('e'):rep(32)
 local bind_id,apply_id,digest=('f'):rep(32),('1'):rep(32),('2'):rep(64)
 local sock={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
 local writer
 local owner
 local saved={enabled=true,baseline=10054,guard=function()
  if mode=='reentrant' and owner and owner:state()=='applying' then pcall(function()owner:tick()end) end
  return guard_ok
 end,register=function(f)callbacks.saved=f;return true end,
  factory=function(opt)return {begin=function()return true end,tick=function()return true end,event=function(_,v)
   assert(v=='ok');assert(opt.capture_binding('42','43','44',1318,1));return opt.complete({epoch=epoch,generation=generation,index=1318,sequence=1,sector_macro='cluster_115_sector001_macro'})
  end}end}
 owner=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,nonce=nonce,
  timeout=5,max_age=2,max_tracks=10,clock=function()return now end,guard=function()return healthy end,net=sock,fault=function(reason)faults[#faults+1]=reason end,
  register=function(f)callbacks.replica=f;return true end,factory=function()error('replica')end,saved_baseline=saved,
  buffer={new=function()return {push=function()return true end}end},
  saved_apply={enabled=true,register=function(f)callbacks.apply=f;return true end,factory=function(opt)
   writer=assert(writer_module.new({enabled=true,timeout=5,clock=function()return now end,game=function()return game end,guard=opt.guard,
    issue=function(id)callbacks.last_id=id;if mode=='dispatch_error' then error('opaque')end;return true end,
    inspect=function()if mode=='inspect_error' then error('opaque') end;if writes==0 then return {x=mode=='short_distance' and 9 or 0,y=0,z=0,yaw=math.pi/2,pitch=0,roll=0}end
     return {x=mode=='bad_readback' and 100 or 10,y=0,z=0,yaw=0,pitch=0,roll=0}end,
    write=function(_,target)writes=writes+1;assert(math.abs(target.yaw-90)<1e-9);if mode=='write_error' then error('partial')end;return true end,
    log=function(line)logs[#logs+1]=line;return true end,fault=opt.fault}));return writer
  end}}))
 assert(owner:start())
 input[1]=table.concat({'M',lease,attempt,'BIND',bind_id,epoch,generation,'1318','1','cluster_115_sector001_macro',digest,'10','10','0','0','-','-','-'},'|')
 assert(owner:tick());callbacks.saved(nil,'ok');assert(owner:state()=='ready' and #out==2 and out[2]:find('|BOUND|',1,true))
 if mode=='stale' then now=4 end
 input[1]=table.concat({'M',lease,attempt,'APPLY',apply_id,epoch,generation,'1318','1',mode=='wrong_digest' and ('3'):rep(64) or digest},'|')
 if mode=='stale' or mode=='wrong_digest' or mode=='reentrant' or mode=='dispatch_error' then assert(not owner:tick());assert(writes==0 and #out==2);if mode=='dispatch_error' then assert(faults[1]=='apply_dispatch_issue') end;return end
 assert(owner:tick() and callbacks.last_id==apply_id..'-pre' and #out==2)
 if mode=='baseline_lost' then guard_ok=false end
 if mode=='wrong_event' then callbacks.apply(nil,apply_id..'-post|ok') else callbacks.apply(nil,apply_id..'-pre|ok')end
 if mode=='baseline_lost' or mode=='wrong_event' or mode=='inspect_error' or mode=='short_distance' then
  assert(owner:state()=='failed' and writes==0 and #out==2)
  if mode=='wrong_event' then assert(faults[1]=='apply_pre_response') end
  if mode=='inspect_error' then assert(faults[1]=='apply_pre_inspect') end
  if mode=='short_distance' then assert(faults[1]=='apply_pre_distance') end
  return
 end
 if mode=='write_error' then assert(owner:state()=='failed' and writes==1 and #out==2 and faults[1]=='apply_write');return end
 assert(writes==1 and writer:state()=='settling' and #out==2)
 now=1.5;assert(owner:tick() and callbacks.last_id==apply_id..'-pre' and #out==2)
 if mode=='stale_after_write' then now=4;assert(not owner:tick() and writes==1 and #out==2);return end
 now=2.1;game=11;assert(owner:tick() and callbacks.last_id==apply_id..'-post' and #out==2)
 callbacks.apply(nil,apply_id..'-post|ok');if mode=='bad_readback' then assert(owner:state()=='failed' and writes==1 and #out==2);return end
 assert(writer:state()=='done' and #out==2)
 assert(owner:tick() and #out==3 and out[3]==table.concat({'R',lease,attempt,'APPLIED',apply_id,epoch,generation,'1318','1',digest},'|'))
 assert(#logs==3 and logs[1]:match('^INTENT ') and logs[2]:match('^WRITE_ENTERED ') and logs[3]:match('^READBACK '))
 input[1]=table.concat({'M',lease,attempt,'APPLY',apply_id,epoch,generation,'1318','1',digest},'|');assert(not owner:tick() and writes==1)
end
for _,mode in ipairs({'ok','stale','wrong_digest','wrong_event','baseline_lost','write_error','reentrant','stale_after_write','bad_readback','dispatch_error','inspect_error','short_distance'})do rig(mode)end
print('one-shot saved motion apply tests passed')
