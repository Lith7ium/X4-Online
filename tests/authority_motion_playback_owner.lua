-- Real owner/controller/buffer, fake engine and asynchronous local binding.
local owner_module=dofile('src/authority/lua/motion_client_owner.lua')
local playback=dofile('src/authority/lua/motion_playback.lua')
local buffer=dofile('src/authority/lua/motion_buffer.lua')
local lease,attempt,epoch,generation,nonce=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32),('e'):rep(32)

local function exercise(mode)
 local now,sequence=1,nil
 local is_paused=mode=='paused'
 local input,output,controllers,events={},{},{},{}
 local saved_callback,binding_options
 local actual={x=0,y=0,z=0,yaw=.5,pitch=.1,roll=.2}
 local writes=0
 local function all_stopped()
  for _,controller in ipairs(controllers)do assert(controller:state()=='stopped' or controller:state()=='failed')end
 end
 local owner=assert(owner_module.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,nonce=nonce,
  timeout=3,max_age=2,max_tracks=1,clock=function()return now end,guard=function()return true end,
  buffer=buffer,register=function()return true end,factory=function()error('replica route forbidden')end,
  fault=function()all_stopped();events[#events+1]='fault'end,
  stop=function()all_stopped();events[#events+1]='transport';return true end,
  net={send=function(_,packet)output[#output+1]=packet;return true end,receive=function()return table.remove(input,1)end},
  saved_baseline={enabled=true,baseline=1318,guard=function()return true end,
   register=function(callback)saved_callback=callback;return true end,
   factory=function(options)
    binding_options=options
    return {begin=function(_,request)sequence=request.sequence;return true end,tick=function()return true end,
     event=function()
      local actor=mode=='actor_change' and sequence==2 and '42' or '41'
      assert(options.capture_binding(actor,'43','45',1318,sequence))
      assert(options.complete({epoch=epoch,generation=generation,index=1318,sequence=sequence,sector_macro='sector_a'}))
      return true
     end,
     close=function()all_stopped();events[#events+1]='binding';return true end}
   end},
  saved_playback={enabled=true,factory=function(options)
   assert(options.sample_version==(mode=='v3' and 3 or 1))
   local controller=assert(playback.new({enabled=true,buffer=options.buffer,frame=options.binding.sector_macro,sample_version=options.sample_version,
    max_age=options.max_age,max_step=50,clock=options.clock,game=function()return now+100 end,
    paused=function()return is_paused end,guard=options.guard,record=function()return true end,fault=options.fault,
    read=function()return actual end,write=function(target)
     writes=writes+1;actual.x=target.x
     if mode=='write_failure' then error('partial')end
     return true
    end}))
   controllers[#controllers+1]=controller;return controller
  end}}))
 local function packet(number,x)
  local fields={'M',lease,attempt,mode=='v3' and 'BIND3' or 'BIND',string.format('%032x',number),epoch,generation,'1318',tostring(number),
   'sector_a',('1'):rep(64),tostring(10000+number*.2)}
  if mode=='v3' then fields[#fields+1]=tostring(number*.2) end
  for _,v in ipairs({tostring(x),'0','0','-','-','-'})do fields[#fields+1]=v end
  return table.concat(fields,'|')
 end
 assert(owner:start())
 input[1]=packet(1,10);assert(owner:tick())
 if mode=='expired' then now=3.1 end
 saved_callback(nil,'bound')
 if mode=='paused' or mode=='expired' then
  assert(owner:state()=='ready' and #output==2 and output[2]:find('|BOUND|',1,true))
  assert(owner:tick() and writes==0)
  is_paused=false;now=now+.1;assert(owner:tick() and writes==0)
  now=now+.1;input[1]=packet(2,10);assert(owner:tick())
  now=now+.1;saved_callback(nil,'fresh')
  assert(owner:tick() and writes==1 and actual.x==10 and #controllers==1)
  input[1]=table.concat({'M',lease,attempt,'STOP',('f'):rep(32),epoch,generation},'|')
  assert(owner:tick() and owner:state()=='stopped' and writes==1)
  return
 end
 if mode=='write_failure' then
  assert(not owner:tick() and owner:state()=='failed' and owner:outcome_uncertain() and writes==1)
  assert(not owner:tick() and writes==1);return
 end
 assert(owner:tick() and writes==1)
 now=1.1;input[1]=packet(2,20);assert(owner:tick())
 -- While MD binding is pending, the existing owner still renders the old track.
 now=1.2;actual.x=7;assert(owner:tick() and writes==2 and owner:state()=='pending')
 now=1.3;saved_callback(nil,'bound')
 if mode=='actor_change' then
  assert(owner:state()=='failed');all_stopped();assert(not owner:tick() and writes==2);return
 end
 assert(owner:state()=='ready' and owner:tick() and writes==3 and #controllers==1)
 input[1]=table.concat({'M',lease,attempt,'STOP',('f'):rep(32),epoch,generation},'|')
 assert(owner:tick() and owner:state()=='stopped' and writes==3)
 assert(events[1]=='binding' and events[2]=='transport')
 assert(owner:outcome_uncertain()) -- STOP preserves the unmeasured last write.
 saved_callback(nil,'late event');assert(owner:state()=='failed' and writes==3)
end
for _,mode in ipairs({'normal','v3','actor_change','write_failure','paused','expired'})do exercise(mode)end
print('real owner playback, deferred binding, fixed actor and ordered STOP passed')
