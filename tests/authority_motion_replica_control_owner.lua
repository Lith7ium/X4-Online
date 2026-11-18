-- Real motion owner; simulated async replica control, binding and playback.
local module=dofile('src/authority/lua/motion_client_owner.lua')
local lease,attempt,epoch,generation,nonce=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32),('e'):rep(32)

local function fixture(mode)
 local x={now=1,input={},output={},events={},control_ticks=0,playback_ticks=0,
  prepares=0,mutations=0,creates=0,guard=true,control_state='new',playback_state='new'}
 local callback,request,options
 local function event(name)x.events[#x.events+1]=name end
 local config={enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,nonce=nonce,
  timeout=3,max_age=.5,max_tracks=1,clock=function()return x.now end,guard=function()return x.guard end,
  buffer={new=function()error('playback must own buffering')end},register=function()return true end,
  factory=function()error('replica route forbidden')end,
  fault=function(_,uncertain)
   assert(x.creates==0 or x.playback_state=='stopped')
   x.fault_uncertain=uncertain;event('fault')
  end,
  stop=function()assert(x.creates==0 or x.playback_state=='stopped');event('transport');return true end,
  net={send=function(_,packet)x.output[#x.output+1]=packet;event('send');return true end,
   receive=function()return table.remove(x.input,1)end},
  saved_baseline={enabled=true,baseline=1318,guard=function()return true end,
   register=function(fn)callback=fn;return true end,
   factory=function(opt)return {
    begin=function(_,value)request=value;return true end,tick=function()return true end,
    event=function()
     local actor=mode=='actor_change' and request.sequence==2 and '99' or '41'
     assert(opt.capture_binding(actor,'43','45',1318,request.sequence))
     assert(opt.complete({epoch=epoch,generation=generation,index=1318,sequence=request.sequence,sector_macro='sector_a'}))
     return true
    end,
    close=function()assert(x.playback_state=='stopped');event('binding');return true end}
   end},
  saved_playback={enabled=true,factory=function(opt)
   x.creates=x.creates+1;x.playback_options=opt
   assert(x.control_state=='prepared');event('playback')
   return {
    push=function(_,snapshot,arrival)
     assert(opt.guard());x.arrival=arrival;x.sequence=snapshot.sequence;event('push')
     if x.now-arrival>=.5 then x.playback_state='stale';return false,'expired' end
     x.playback_state='active';return true
    end,
    tick=function()
     assert(x.playback_state~='stopped' and opt.guard())
     x.playback_ticks=x.playback_ticks+1;event('write');return true
    end,
    stop=function()x.playback_state='stopped';event('disable');return true end,
    state=function()return x.playback_state end,
    outcome_uncertain=function()return x.write_uncertain==true end}
   end},
  saved_replica_control={enabled=true,factory=function(opt)
   options=opt;x.control_options=opt
   assert(opt.binding.actor_key=='41' and opt.binding.sector_key=='43' and opt.binding.zone_key=='45')
   assert(opt.binding.index==1318 and opt.binding.epoch==epoch and opt.binding.sector_macro=='sector_a')
   assert(opt.nonce==nonce and opt.timeout==3 and opt.clock()==1)
   if mode=='factory_fault' then opt.fault('factory',true) end
   return {
    prepare=function()
     assert(opt.guard());x.prepares=x.prepares+1;event('prepare')
     if x.control_state=='new' then
      x.mutations=x.mutations+1;x.control_state='preparing'
      if mode=='prepare_failure' then x.control_state='failed';opt.fault('prepare',true);return false end
     elseif mode=='revalidate_failure' then
      x.control_state='failed';opt.fault('revalidate',true);return false
     else assert(x.control_state=='prepared')end
     return true
    end,
    tick=function()
     assert(opt.guard());x.control_ticks=x.control_ticks+1;event('control_tick')
     if mode=='tick_failure' and x.control_state=='prepared' then
      x.control_state='failed';opt.fault('hold_expired',true);return false
     end
     if x.control_state=='preparing' and x.complete_prepare then x.control_state='prepared' end
     if x.control_state=='releasing' and x.complete_release then x.control_state='released' end
     return true
    end,
    state=function()return x.control_state end,
    release=function()
     assert(opt.guard() and x.playback_state=='stopped' and x.events[#x.events]=='transport')
     event('release');x.control_state='releasing'
     if mode=='release_failure' then x.control_state='failed';opt.fault('release',true);return false end
     return true
    end,
    outcome_uncertain=function()
     return x.control_state=='preparing' or x.control_state=='releasing' or x.control_state=='failed'
    end}
   end}}
 x.config=config
 function x:packet(sequence)
  return table.concat({'M',lease,attempt,'BIND',string.format('%032x',sequence),epoch,generation,'1318',tostring(sequence),
   'sector_a',('1'):rep(64),tostring(100+sequence),'10','0','0','-','-','-'},'|')
 end
 function x:bind(sequence)
  self.input[1]=self:packet(sequence);assert(self.owner:tick());callback(nil,'bound')
 end
 function x:stop()
  self.input[1]=table.concat({'M',lease,attempt,'STOP',('f'):rep(32),epoch,generation},'|')
  return self.owner:tick()
 end
 function x:prepared()
  self:bind(1);assert(self.owner:state()=='preparing' and #self.output==1 and self.creates==0)
  self.now=1.1;assert(self.owner:tick() and self.control_ticks==1 and self.creates==0)
  self.complete_prepare=true;self.now=1.2;assert(self.owner:tick())
  assert(self.owner:state()=='ready' and self.creates==1 and self.arrival==1)
  assert(self.output[2]:find('|BOUND|',1,true) and self.playback_ticks==0)
  assert(not self.owner:outcome_uncertain())
 end
 x.owner=assert(module.new(config));assert(x.owner:start())
 return x
end

-- First prepare is async and preserves original arrival; later binds revalidate
-- once without another mutation. Controller tick always precedes writer tick.
do
 local x=fixture();x:prepared()
 assert(x.owner:tick() and x.control_ticks==3 and x.playback_ticks==1)
 assert(x.events[#x.events-1]=='control_tick' and x.events[#x.events]=='write')
 x:bind(2);assert(x.owner:state()=='ready' and x.prepares==2 and x.mutations==1)
 x.playback_state='stale';local writes=x.playback_ticks
 assert(x:stop() and x.owner:state()=='stopping' and x.playback_state=='stopped')
 assert(not x.output[#x.output]:find('|STOPPED|',1,true))
 local ticks=x.control_ticks
 assert(x.owner:tick() and x.control_ticks==ticks+1 and x.playback_ticks==writes)
 x.complete_release=true;assert(x.owner:tick() and x.owner:state()=='stopped')
 assert(x.output[#x.output]:find('|STOPPED|',1,true) and not x.owner:outcome_uncertain())
 assert(x.owner:tick() and x.playback_ticks==writes)
end
-- Delayed preparation must not refresh the enrollment packet's arrival time.
do
 local x=fixture();x:bind(1);x.now=1.7;x.complete_prepare=true
 assert(x.owner:tick() and x.owner:state()=='ready' and x.arrival==1 and x.playback_state=='stale')
end
-- No controller was started: ordinary STOP works without a release handshake.
do
 local x=fixture();assert(x:stop() and x.owner:state()=='stopped' and x.prepares==0)
end
-- Pending and failed control effects propagate uncertainty without any writer.
for _,mode in ipairs({'prepare_failure','factory_fault'})do
 local x=fixture(mode);x:bind(1)
 assert(x.owner:state()=='failed' and x.creates==0 and x.owner:outcome_uncertain() and x.fault_uncertain)
end
-- Reject a changed actor before invoking prepare again.
do
 local x=fixture('actor_change');x:prepared();x:bind(2)
 assert(x.owner:state()=='failed' and x.prepares==1 and x.playback_state=='stopped')
end
for _,mode in ipairs({'revalidate_failure','tick_failure','release_failure'})do
 local x=fixture(mode);x:prepared()
 if mode=='revalidate_failure' then x:bind(2)
 elseif mode=='tick_failure' then assert(not x.owner:tick())
 else x.playback_state='stale';assert(not x:stop())end
 assert(x.owner:state()=='failed' and x.playback_state=='stopped' and x.owner:outcome_uncertain())
 assert(x.fault_uncertain)
end
-- STOP cannot release a track still active or with an unmeasured write.
for _,mode in ipairs({'active','uncertain'})do
 local x=fixture();x:prepared()
 if mode=='uncertain' then x.playback_state='stale';x.write_uncertain=true end
 assert(not x:stop() and x.owner:state()=='failed' and x.playback_state=='stopped')
 assert(x.control_state=='prepared' and not x.output[#x.output]:find('|STOPPED|',1,true))
 assert(x.owner:outcome_uncertain() and x.fault_uncertain)
end
-- A prepared but unreleased Wait is unresolved on terminal packet failure,
-- even though the adapter's last confirmed-held operation was itself certain.
do
 local x=fixture();x:prepared();x.input[1]='unexpected'
 assert(not x.owner:tick() and x.owner:state()=='failed' and x.control_state=='prepared')
 assert(x.owner:outcome_uncertain() and x.fault_uncertain and x.playback_state=='stopped')
end
-- Extra packets, deadlines and guards fail closed in both asynchronous phases.
for _,phase in ipairs({'prepare','release'})do
 for _,failure in ipairs({'packet','deadline','guard'})do
  local x=fixture()
  if phase=='prepare' then x:bind(1)
  else x:prepared();x.playback_state='stale';assert(x:stop())end
  if failure=='packet' then x.input[1]=x:packet(2)
  elseif failure=='deadline' then x.now=10
  else x.guard=false end
  assert(not x.owner:tick() and x.owner:state()=='failed' and x.owner:outcome_uncertain())
  assert(x.creates==0 or x.playback_state=='stopped')
  assert(not x.output[#x.output]:find('|STOPPED|',1,true))
 end
end
-- Opt-in configuration cannot attach control to generic/multi-track ownership.
for _,change in ipairs({'playback','tracks'})do
 local x=fixture()
 x.config.net={send=function()return true end,receive=function()end}
 if change=='playback' then x.config.saved_playback=nil else x.config.max_tracks=2 end
 assert(not pcall(module.new,x.config))
end
print('async saved replica control owner preparation, drain, release and fencing passed')
