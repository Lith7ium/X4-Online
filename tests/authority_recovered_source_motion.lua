-- Real source IPC, sampler, bootstrap and shutdown with simulated X4 and UDP.
local M=dofile('tools/dev/authority_recovered_source_motion.lua')
local B=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local S=dofile('src/authority/lua/source_motion_sampler.lua')
local I=dofile('src/authority/lua/source_motion_ipc.lua')
local G=dofile('src/authority/lua/source_motion_shutdown.lua')
local C=dofile('tools/dev/authority_registry_motion_candidate.lua')
local lease,attempt,epoch,gen,nonce,saved=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32),string.rep('e',32),string.rep('f',32)
local function rig(with_selection)
 local now=1;local paused=false;local alive=true;local input,out,events,issued,faults={},{},{},{},{}
 local reports={};local selection,selector_obj
 if with_selection then selection={nonce=string.rep('9',32),candidates={1,2},
  register=function(f)events[2]=f;return true end,report=function(r)
   reports[#reports+1]=r;if with_selection=='mutate' then r.index=2 end
   if with_selection=='mutate_original' then selector_obj:result().index=2 end
   if with_selection=='metatable' then r.index=nil;setmetatable(r,{__index={index=1}})end
   if with_selection=='reenter' then selector_obj:event('late')end;return true
  end,
  factory=function(o)
   o.timeout=5;o.clock=function()return now end;o.issue=function(_,_,v)issued[#issued+1]={kind='candidate',args=v};return true end
   o.inspect=function()return 'eligible'end;selector_obj=C.new(o);return selector_obj
  end}
 end
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end,pending=function()return #input>0 end}
 local session=assert(M.new({enabled=true,epoch=epoch,generation=gen,nonce=nonce,saved_nonce=saved,baseline=2,selection=selection,
  running=function()return not paused end,guard=function()return alive end,register=function(f)events[1]=f;return true end,
  fault=function(v)faults[#faults+1]=v end,
  bootstrap_factory=function(o)
   o.timeout=5;o.clock=function()return now end
   o.issue=function(_,_,v)issued[#issued+1]={kind='bootstrap',args=v};return true end
   o.parse=function(v)return v end;o.inspect=function()return true end;return B.new(o)
  end,
  sampler_factory=function(o)
   o.clock=function()return now end;o.max_tracks=1;o.scan_budget=1;o.interval=.1;o.timeout=5;o.min_dt=.02;o.max_dt=2
   o.actor_key=function()return '1'end
   o.reader_factory=function(row,actor,request)
    return {start=function()issued[#issued+1]={kind='sample',request=request};return true end,
     tick=function()return true end,response=function()
      return true,{epoch=epoch,index=row.index,sequence=row.sequence,descriptor_atomic=false,sector_identity_proven=false,
       sector_macro='sector_a',local_sector_key='42',game_before_pose=now,game_after_pose=now,x=now,y=2,z=3}
     end}
   end
   return S.new(o)
  end,
  ipc_factory=function(o)o.enabled=true;o.lease=lease;o.attempt=attempt;o.epoch=epoch;o.generation=gen;o.timeout=5;o.clock=function()return now end;o.net=net;return I.new(o)end,
  shutdown_factory=G.new}))
 return session,input,out,events,issued,faults,function(v)paused=v end,function(v)now=v end,function(v)alive=v end,reports
end
local suffix='|'..epoch..'|'..gen
local function request_candidate(app,input)
 input[1]='P|'..lease..'|'..attempt..'|CANDIDATE'..suffix..'|1'
 assert(app:tick());return app:tick()
end
-- A pending request waits for selection; no candidate packet is unsolicited.
do
 local app,input,out,events,issued=rig(true)
 assert(#out==1 and out[1]:find('|HELLO|',1,true))
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(app:tick() and #out==2)
 input[1]='P|'..lease..'|'..attempt..'|CANDIDATE'..suffix..'|1';assert(app:tick() and #out==2)
 local q=issued[1].args;events[2](q.request_id..'|'..epoch..'|1|ok|0x1|0x2|sector_a')
 assert(app:tick());assert(out[#out]=='S|'..lease..'|'..attempt..'|CANDIDATE'..suffix..'|1|candidate|1')
 input[1]='P|'..lease..'|'..attempt..'|CANDIDATE'..suffix..'|2';assert(not app:tick())
end
-- A request before BOUND never produces a report.
do
 local app,input,out=rig(true)
 input[1]='P|'..lease..'|'..attempt..'|CANDIDATE'..suffix..'|1'
 assert(not app:tick());assert(#out==1 and out[1]:find('|HELLO|',1,true))
end
-- A queued follow-up fences the result before any candidate acknowledgement.
for _,followup in ipairs({'', 'P|'..lease..'|'..attempt..'|PULL'..suffix..'|2'})do
 local app,input,out,events,issued=rig(true)
 local q=issued[1].args;events[2](q.request_id..'|'..epoch..'|1|ok|0x1|0x2|sector_a')
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(app:tick())
 input[1]='P|'..lease..'|'..attempt..'|CANDIDATE'..suffix..'|1'
 input[2]=followup
 assert(app:tick());assert(not app:tick() and app:state()=='failed')
 for _,v in ipairs(out)do assert(not v:find('|CANDIDATE|',1,true))end
end
local function initial()
 local app,input,out,events,issued,faults,pause,clock=rig()
 assert(out[1]=='S|'..lease..'|'..attempt..'|HELLO'..suffix)
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(app:tick())
 input[1]='P|'..lease..'|'..attempt..'|REGISTER_SAVED'..suffix..'|1|1|2';assert(app:tick())
 assert(issued[1].kind=='bootstrap');local id=issued[1].args.request_id
 events[1](id..'|'..epoch..'|1|ok|0x1|ship_a|argon|0x2|sector_a')
 assert(out[#out]=='S|'..lease..'|'..attempt..'|SAVED_REGISTERED'..suffix..'|1|1|2')
 return app,input,out,events,issued,faults,pause,clock
end
do
 local app,input,out,events,issued,faults,pause,clock=initial()
 input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|2';assert(app:tick())
 assert(issued[2].kind=='sample');events[1](issued[2].request..'|ok');assert(out[#out]:find('|SAMPLE|',1,true))
 clock(2);input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|3';assert(app:tick())
 events[1](issued[3].request..'|ok');assert(out[#out]:match('|1|0|0$')) -- velocity from positions/game seconds
 input[1]='P|'..lease..'|'..attempt..'|STOP'..suffix..'|4';assert(app:tick() and app:state()=='stopped')
 assert(out[#out]:find('|STOPPED|',1,true));pause(true);assert(app:tick())
 events[1]('late');assert(app:state()=='failed' and #faults>=1);assert(not app:tick())
end
-- Pause loss before STOP and a foreign event fail, with no shutdown receipt.
do local app,_,out,events,_,faults,pause=initial();pause(true);assert(not app:tick() and app:state()=='failed' and #faults>=1)
 for _,v in ipairs(out)do assert(not v:find('|STOPPED|',1,true))end end
do local app,_,_,events,_,faults=initial();events[1](string.rep('9',32)..'|stale');assert(app:state()=='failed' and #faults>=1)end
-- STOP arriving with a descriptor/sample in flight cannot acknowledge closure.
do
 local app,input,out,_,_,faults=initial()
 input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|2';assert(app:tick())
 input[1]='P|'..lease..'|'..attempt..'|STOP'..suffix..'|3';assert(not app:tick() and app:state()=='failed')
 for _,v in ipairs(out)do assert(not v:find('|STOPPED|',1,true))end;assert(#faults>=1)
end

-- Motion generation and nonce must not collide even if the installer is bypassed.
assert(not pcall(M.new,{enabled=true,epoch=epoch,generation=gen,nonce=gen,saved_nonce=saved,baseline=2}))

-- A post-stop empty UDP datagram still faults, even after the game pauses.
do
 local app,input,out,_,_,faults,pause=initial()
 input[1]='P|'..lease..'|'..attempt..'|STOP'..suffix..'|2';assert(app:tick() and app:state()=='stopped')
 pause(true);input[1]='';assert(not app:tick() and app:state()=='failed' and #faults>=1)
end

-- The optional selector has its own event name, while descriptors retain the
-- original sole handler. Only the selected index can reach bootstrap.
do
 local app,input,out,events,issued,faults,_,_,_,reports=rig(true)
 assert(events[1] and events[2] and issued[1].kind=='candidate')
 local q=issued[1].args;events[2](q.request_id..'|'..epoch..'|1|ineligible')
 q=issued[2].args;events[2](q.request_id..'|'..epoch..'|2|ok|0x1|0x2|sector_a')
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(app:tick())
 assert(#reports==0 and #out==2)
 assert(request_candidate(app,input));assert(out[#out]=='S|'..lease..'|'..attempt..'|CANDIDATE'..suffix..'|1|candidate|2')
 assert(#reports==1 and reports[1].index==2)
 input[1]='P|'..lease..'|'..attempt..'|REGISTER_SAVED'..suffix..'|2|2|2';assert(app:tick())
 assert(issued[3].kind=='bootstrap' and issued[3].args.index==2)
 q=issued[3].args;events[1](q.request_id..'|'..epoch..'|2|ok|0x1|ship_a|argon|0x2|sector_a')
 assert(out[#out]:find('|SAVED_REGISTERED|',1,true) and #faults==0)
 input[1]='P|'..lease..'|'..attempt..'|STOP'..suffix..'|3';assert(app:tick() and app:state()=='stopped')
 events[2]('late');assert(app:state()=='failed')
end
do
 local app,input,out,events,issued=rig(true)
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(app:tick())
 input[1]='P|'..lease..'|'..attempt..'|REGISTER_SAVED'..suffix..'|1|1|2';assert(not app:tick() and app:state()=='failed')
 assert(#issued==1)
end
do
 local app,input,out=rig(true)
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(app:tick())
 input[1]='P|'..lease..'|'..attempt..'|STOP'..suffix..'|1';assert(not app:tick() and app:state()=='failed')
 for _,v in ipairs(out)do assert(not v:find('|STOPPED|',1,true))end
end
do
 local app,input,_,events,issued=rig(true)
 local q=issued[1].args;events[2](q.request_id..'|'..epoch..'|1|ok|0x1|0x2|sector_a')
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(app:tick())
 assert(request_candidate(app,input))
 input[1]='P|'..lease..'|'..attempt..'|REGISTER_SAVED'..suffix..'|2|2|2';assert(not app:tick() and app:state()=='failed')
end
do
 local app,input,_,events,issued,_,_,_,_,reports=rig(true)
 for i=1,2 do local q=issued[i].args;events[2](q.request_id..'|'..epoch..'|'..i..'|ineligible')end
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(app:tick())
 assert(request_candidate(app,input))
 assert(reports[1].status=='inconclusive')
 input[1]='P|'..lease..'|'..attempt..'|REGISTER_SAVED'..suffix..'|2|1|2';assert(not app:tick() and app:state()=='failed')
end
do
 local app,input,_,events,issued=rig('mutate')
 local q=issued[1].args;events[2](q.request_id..'|'..epoch..'|1|ok|0x1|0x2|sector_a')
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix
 assert(app:tick());assert(not request_candidate(app,input) and app:state()=='failed')
end
do
 local app,input,_,events,issued=rig('reenter')
 local q=issued[1].args;events[2](q.request_id..'|'..epoch..'|1|ok|0x1|0x2|sector_a')
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix
 assert(app:tick());assert(not request_candidate(app,input) and app:state()=='failed')
end
for _,kind in ipairs({'mutate_original','metatable'})do
 local app,input,_,events,issued=rig(kind)
 local q=issued[1].args;events[2](q.request_id..'|'..epoch..'|1|ok|0x1|0x2|sector_a')
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix
 assert(app:tick());assert(not request_candidate(app,input) and app:state()=='failed')
end
