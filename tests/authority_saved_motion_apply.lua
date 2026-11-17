local writer_module=dofile('src/authority/lua/saved_motion_apply.lua')
local owner_module=dofile('src/authority/lua/motion_client_owner.lua')
local function rig(mode)
 local now,game=1,10;local callbacks,input,out,logs,faults={}, {}, {}, {}, {}; local writes=0;local guard_ok=true;local healthy=true;local near_override=mode=='near_rebind_ready'
 local lease,attempt,epoch,generation,nonce=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32),('e'):rep(32)
 local bind_id,apply_id,digest=('f'):rep(32),('1'):rep(32),('2'):rep(64)
 local sock={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
 local writer
 local owner
 local saved={enabled=true,baseline=10054,guard=function()
  if mode=='reentrant' and owner and owner:state()=='applying' then pcall(function()owner:tick()end) end
  return guard_ok
 end,register=function(f)callbacks.saved=f;return true end,
  factory=function(opt)local sequence;return {begin=function(_,v)sequence=v.sequence;return true end,tick=function()return true end,event=function(_,v)
   assert(v=='ok');assert(opt.capture_binding('42','43','44',1318,sequence));return opt.complete({epoch=epoch,generation=generation,index=1318,sequence=sequence,sector_macro='cluster_115_sector001_macro'})
  end}end}
 owner=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,nonce=nonce,
  timeout=5,max_age=2,max_tracks=10,clock=function()return now end,guard=function()return healthy end,net=sock,fault=function(reason)faults[#faults+1]=reason end,
  register=function(f)callbacks.replica=f;return true end,factory=function()error('replica')end,saved_baseline=saved,
  buffer={new=function()return {push=function()return true end}end},
  saved_apply={enabled=true,immediate_readback=mode:match('^immediate_') and true or nil,register=function(f)callbacks.apply=f;return true end,factory=function(opt)
   writer=assert(writer_module.new({enabled=true,readonly=opt.readonly,immediate_readback=opt.immediate_readback,timeout=5,clock=function()return now end,game=function()return mode=='immediate_time' and writes>0 and 9 or game end,guard=opt.guard,
    issue=function(id)callbacks.last_id=id;if mode=='dispatch_error' and not opt.readonly then error('opaque')end;return true end,
    inspect=function()if mode=='inspect_error' and not opt.readonly or mode=='immediate_fault' and writes>0 then error('opaque') end;if writes==0 then return {x=mode=='short_distance' and not opt.readonly and 9 or ((mode=='pre_near' or near_override) and 9 or (mode=='pre_far' and 100 or (mode=='pre_boundary_5' and 5 or (mode=='pre_boundary_50' and -40 or 0)))),y=0,z=0,yaw=math.pi/2,pitch=0,roll=0}end
     return {x=(mode=='bad_readback' or mode=='immediate_bad') and 100 or 10,y=0,z=0,yaw=0,pitch=0,roll=0}end,
    write=function(_,target)writes=writes+1;assert(math.abs(target.yaw-90)<1e-9);if mode=='write_error' then error('partial')end;return true end,
    log=function(line)logs[#logs+1]=line;return true end,fault=opt.fault}));return writer
  end}}))
 assert(owner:start())
 input[1]=table.concat({'M',lease,attempt,'BIND',bind_id,epoch,generation,'1318','1','cluster_115_sector001_macro',digest,'10','10','0','0','-','-','-'},'|')
 assert(owner:tick());callbacks.saved(nil,'ok');assert(owner:state()=='ready' and #out==2 and out[2]:find('|BOUND|',1,true))
 if mode=='apply_without_preflight' then
  input[1]=table.concat({'M',lease,attempt,'APPLY',apply_id,epoch,generation,'1318','1',digest},'|')
  assert(not owner:tick() and writes==0 and #out==2);return
 end
 local pre_id=('9'):rep(32)
 if mode=='preflight_after_sample_expired' then now=4 end
 input[1]=table.concat({'M',lease,attempt,'PREFLIGHT',pre_id,epoch,generation,'1318','1',digest},'|')
 if mode=='preflight_after_sample_expired' then
  -- BIND has been acknowledged, but the sample is older than max_age=2.
  assert(not owner:tick())
  assert(faults[1]=='preflight_begin_guard')
  assert(writes==0 and #logs==0 and #out==2)
  assert(owner:state()=='failed')
  assert(input[1]==nil) -- The failed attempt consumed the original request.
  input[1]=table.concat({'M',lease,attempt,'PREFLIGHT',pre_id,epoch,generation,'1318','1',digest},'|')
  assert(not owner:tick() and owner:state()=='failed')
  input[1]=table.concat({'M',lease,attempt,'APPLY',apply_id,epoch,generation,'1318','1',digest},'|')
  assert(not owner:tick() and owner:state()=='failed')
  assert(writes==0 and #logs==0 and #out==2 and #faults==1)
  return
 end
 assert(owner:tick() and callbacks.last_id==pre_id..'-pre' and writes==0)
 callbacks.apply(nil,pre_id..'-pre|ok')
 if mode=='pre_far' then assert(owner:state()=='failed' and writes==0 and #out==2 and faults[1]=='preflight_pre_distance' and #logs==1 and logs[1]:match(' 90 FAR$'));return end
 assert(owner:tick() and #out==3 and out[3]:find('|PREFLIGHTED|',1,true) and writes==0)
 assert(out[3]:sub(-4)==((mode=='pre_near' or mode=='near_rebind_ready') and 'NEAR' or 'EADY'))
 if mode=='pre_near' then
  input[1]=table.concat({'M',lease,attempt,'APPLY',apply_id,epoch,generation,'1318','1',digest},'|')
  assert(not owner:tick() and writes==0 and #logs==1 and logs[1]:match(' 1 NEAR$'));return
 end
 if mode=='near_rebind_ready' then
  near_override=false
  input[1]=table.concat({'M',lease,attempt,'BIND',('8'):rep(32),epoch,generation,'1318','2','cluster_115_sector001_macro',digest,'11','10','0','0','-','-','-'},'|')
  assert(owner:tick());callbacks.saved(nil,'ok');assert(owner:state()=='ready' and #out==4)
  local second=('7'):rep(32)
  input[1]=table.concat({'M',lease,attempt,'PREFLIGHT',second,epoch,generation,'1318','2',digest},'|')
  assert(owner:tick());callbacks.apply(nil,second..'-pre|ok');assert(owner:tick() and out[#out]:sub(-5)=='READY' and writes==0)
  input[1]=table.concat({'M',lease,attempt,'APPLY',apply_id,epoch,generation,'1318','2',digest},'|')
  assert(owner:tick());callbacks.apply(nil,apply_id..'-pre|ok');assert(writes==1);return
 end
 if mode=='rebind_invalidates' then
  input[1]=table.concat({'M',lease,attempt,'BIND',('8'):rep(32),epoch,generation,'1318','2','cluster_115_sector001_macro',digest,'11','10','0','0','-','-','-'},'|')
  assert(owner:tick());callbacks.saved(nil,'ok');assert(owner:state()=='ready' and #out==4)
  input[1]=table.concat({'M',lease,attempt,'APPLY',apply_id,epoch,generation,'1318','2',digest},'|')
  assert(not owner:tick() and writes==0);return
 end
 if mode=='second_preflight_same_sample' then
  input[1]=table.concat({'M',lease,attempt,'PREFLIGHT',('7'):rep(32),epoch,generation,'1318','1',digest},'|')
  assert(not owner:tick() and writes==0);return
 end
 if mode=='replay_preflight' then
  input[1]=table.concat({'M',lease,attempt,'PREFLIGHT',pre_id,epoch,generation,'1318','1',digest},'|')
  assert(not owner:tick() and writes==0);return
 end
 if mode=='stale' then now=4 end
 input[1]=table.concat({'M',lease,attempt,'APPLY',apply_id,epoch,generation,'1318','1',mode=='wrong_digest' and ('3'):rep(64) or digest},'|')
 if mode=='stale' or mode=='wrong_digest' or mode=='reentrant' or mode=='dispatch_error' then assert(not owner:tick());assert(writes==0 and #out==3);if mode=='dispatch_error' then assert(faults[1]=='apply_dispatch_issue') end;return end
 assert(owner:tick() and callbacks.last_id==apply_id..'-pre' and #out==3)
 if mode=='baseline_lost' then guard_ok=false end
 if mode=='wrong_event' then callbacks.apply(nil,apply_id..'-post|ok') else callbacks.apply(nil,apply_id..'-pre|ok')end
 if mode=='baseline_lost' or mode=='wrong_event' or mode=='inspect_error' or mode=='short_distance' then
  assert(owner:state()=='failed' and writes==0 and #out==3)
  if mode=='wrong_event' then assert(faults[1]=='apply_pre_response') end
  if mode=='inspect_error' then assert(faults[1]=='apply_pre_inspect') end
  if mode=='short_distance' then assert(faults[1]=='apply_pre_distance') end
  return
 end
 if mode=='write_error' then assert(owner:state()=='failed' and writes==1 and #out==3 and faults[1]=='apply_write');return end
 if mode=='immediate_fault' then assert(owner:state()=='failed' and writes==1 and #out==3 and faults[1]=='apply_immediate_inspect');return end
 if mode=='immediate_time' then assert(owner:state()=='failed' and writes==1 and #out==3 and faults[1]=='apply_immediate_game');return end
 assert(writes==1 and writer:state()=='settling' and #out==3)
 now=1.5;assert(owner:tick() and callbacks.last_id==apply_id..'-pre' and #out==3)
 if mode=='stale_after_write' then now=4;assert(not owner:tick() and writes==1 and #out==3);return end
 now=2.1;game=11;assert(owner:tick() and callbacks.last_id==apply_id..'-post' and #out==3)
 callbacks.apply(nil,apply_id..'-post|ok');if mode=='bad_readback' or mode=='immediate_bad' then
  assert(owner:state()=='failed' and writes==1 and #out==3 and faults[1]=='apply_post_readback')
  if mode=='immediate_bad' then assert(logs[#logs]:match('^POST_OBSERVED '..apply_id..' 1318 1 '..digest..' 100 0 0 11 10 ') and logs[#logs]:match(' 90$')) end
  return
 end
 assert(writer:state()=='done' and #out==3)
 assert(owner:tick() and #out==4 and out[4]==table.concat({'R',lease,attempt,'APPLIED',apply_id,epoch,generation,'1318','1',digest},'|'))
 local immediate=mode=='immediate_ok'
 assert(#logs==(immediate and 6 or 4) and logs[1]:match('^PREFLIGHT ') and logs[2]:match('^INTENT ') and logs[3]:match('^WRITE_ENTERED ') and
  (not immediate or (logs[4]:match('^IMMEDIATE ') and logs[5]:match('^POST_OBSERVED '))) and logs[immediate and 6 or 4]:match('^READBACK '))
 input[1]=table.concat({'M',lease,attempt,'APPLY',apply_id,epoch,generation,'1318','1',digest},'|');assert(not owner:tick() and writes==1)
end
local modes = {
 'ok', 'immediate_ok', 'immediate_bad', 'immediate_fault', 'immediate_time',
 'stale', 'wrong_digest', 'wrong_event', 'baseline_lost', 'write_error',
 'reentrant', 'stale_after_write', 'bad_readback', 'dispatch_error',
 'inspect_error', 'short_distance', 'pre_near', 'pre_far', 'pre_boundary_5',
 'pre_boundary_50', 'preflight_after_sample_expired', 'rebind_invalidates',
 'replay_preflight', 'apply_without_preflight', 'near_rebind_ready',
 'second_preflight_same_sample',
}
for _, mode in ipairs(modes) do rig(mode) end
print('one-shot saved motion apply tests passed')
