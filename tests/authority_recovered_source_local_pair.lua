-- Existing source IPC/router/sampler/shutdown with simulated descriptor and net.
local mode=assert(arg[1])
local delivery=mode:match('^delivery_')~=nil
local owner_module=dofile('tools/dev/authority_recovered_source_motion.lua')
local bootstrap_module=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local sampler_module=dofile('src/authority/lua/source_motion_sampler.lua')
local ipc_module=dofile('src/authority/lua/source_motion_ipc.lua')
local shutdown_module=dofile('src/authority/lua/source_motion_shutdown.lua')
local pair_module=dofile('src/authority/lua/source_motion_local_pair.lua')
local lease,attempt,epoch,generation,normal_nonce,saved_nonce,pair_nonce=
 string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32),
 string.rep('e',32),string.rep('f',32),string.rep('9',32)
local now,alive,paused,local_sector=1,true,false,'42'
local actor_key='1'
local incoming,outgoing,events,issued,faults,reports={},{},{},{},{},{}
local session
local net={send=function(_,v)outgoing[#outgoing+1]=v;return true end,
 receive=function()return table.remove(incoming,1)end,pending=function()return #incoming>0 end}
local options={enabled=true,epoch=epoch,generation=generation,nonce=normal_nonce,saved_nonce=saved_nonce,
 baseline=2,timeout=5,clock=function()return now end,
 running=function()return not paused end,guard=function()return alive end,
 register=function(f)events[1]=f;return true end,fault=function(reason)faults[#faults+1]=reason end,
 bootstrap_factory=function(o)
  o.timeout=5;o.clock=function()return now end
  o.issue=function(_,_,v)issued[#issued+1]={kind='bootstrap',request=v.request_id};return true end
  o.parse=function(v)return v end;o.inspect=function()return true end
  return bootstrap_module.new(o)
 end,
 sampler_factory=function(o)
  local nonce=o.nonce
  o.clock=function()return now end;o.max_tracks=1;o.scan_budget=1;o.interval=.1;o.timeout=5;o.min_dt=.02;o.max_dt=1
  o.actor_key=function()return actor_key end
  o.reader_factory=function(row,actor,request)
   return {start=function()issued[#issued+1]={kind=nonce==pair_nonce and 'pair' or 'normal',request=request};return true end,
    tick=function()return true end,
    response=function(_,raw)
     assert(raw==request..'|ok')
     return true,{epoch=epoch,index=row.index,sequence=row.sequence,descriptor_atomic=false,
      sector_identity_proven=false,sector_macro='sector_a',local_sector_key=local_sector,
      game_before_pose=now,game_after_pose=now,x=now*10,y=2,z=3}
    end}
  end
  return sampler_module.new(o)
 end,
 ipc_factory=function(o)o.enabled=true;o.lease=lease;o.attempt=attempt;o.epoch=epoch;o.generation=generation
  o.timeout=5;o.clock=function()return now end;o.net=net;return ipc_module.new(o)end,
 shutdown_factory=shutdown_module.new,
 local_pair={nonce=pair_nonce,index=1,delivery=delivery,factory=pair_module.new,report=function(result)
  reports[#reports+1]=result
  if mode=='mutate' then result.status='forged' end
  if mode=='reenter' then session:tick() end
  return true
 end}}
session=assert(owner_module.new(options))
local suffix='|'..epoch..'|'..generation
local function push(packet)incoming[#incoming+1]=packet;return session:tick()end
local function count(word)
 local n=0;for _,v in ipairs(outgoing)do if v:find('|'..word..'|',1,true)then n=n+1 end end;return n
end
assert(push('P|'..lease..'|'..attempt..'|BOUND'..suffix))
assert(push('P|'..lease..'|'..attempt..'|REGISTER_SAVED'..suffix..'|1|1|2'))
assert(issued[1].kind=='bootstrap')
events[1](issued[1].request..'|'..epoch..'|1|ok|0x1|ship_a|argon|0x2|sector_a')
assert(count('SAVED_REGISTERED')==1)
assert(push('P|'..lease..'|'..attempt..'|PULL'..suffix..'|2'))
assert(issued[2].kind=='pair' and count('SAMPLE')==0)
if mode=='stop_pending' then
 assert(not push('P|'..lease..'|'..attempt..'|STOP'..suffix..'|3'))
 assert(count('STOPPED')==0)
elseif mode=='timeout' then
 now=6;assert(not session:tick() and count('SAMPLE')==0)
elseif mode=='foreign' then
 events[1](pair_nonce:sub(1,16)..string.rep('8',16)..'|ok')
 assert(session:state()=='failed' and count('SAMPLE')==0)
elseif mode=='binding_loss' then
 alive=false;events[1](issued[2].request..'|ok')
 assert(session:state()=='failed' and count('SAMPLE')==0)
else
 events[1](issued[2].request..'|ok')
 assert(session:state()=='active' and count('SAMPLE')==0)
 now=mode=='delivery_unavailable' and 2.2 or 1.2;assert(session:tick());assert(issued[3].kind=='pair')
 if mode=='frame' or mode=='delivery_frame' then local_sector='43' end
 if mode=='delivery_actor' then actor_key='2' end
 events[1](issued[3].request..'|ok')
 if mode=='frame' or mode=='delivery_frame' or mode=='delivery_actor' then
  assert(session:state()=='failed' and count('SAMPLE')==0)
 elseif mode=='mutate' or mode=='reenter' then
  assert(not session:tick() and count('SAMPLE')==0)
 elseif mode=='delivery_unavailable' then
  assert(not session:tick() and count('SAMPLE')==0)
 elseif delivery then
  now=1.3;assert(session:tick())
  assert(#reports==1 and reports[1].status=='estimated')
  assert(#issued==3 and count('SAMPLE')==1)
  local response=outgoing[#outgoing]
  local fields={};for field in (response..'|'):gmatch('(.-)|') do fields[#fields+1]=field end
  assert(#fields==17 and fields[4]=='SAMPLE' and fields[5]==epoch and fields[6]==generation)
  assert(fields[7]=='2' and fields[8]=='1' and fields[9]=='2' and fields[10]=='sector_a')
  assert(tonumber(fields[11])==1.2 and tonumber(fields[12])==12 and tonumber(fields[13])==2 and tonumber(fields[14])==3)
  assert(math.abs(tonumber(fields[15])-10)<1e-8 and tonumber(fields[16])==0 and tonumber(fields[17])==0)
  if mode=='delivery_duplicate' then
   assert(not push('P|'..lease..'|'..attempt..'|PULL'..suffix..'|3'))
   assert(count('SAMPLE')==1 and count('STOPPED')==0)
  else
   assert(push('P|'..lease..'|'..attempt..'|STOP'..suffix..'|3'))
   assert(count('STOPPED')==1 and session:state()=='stopped')
   if mode=='delivery_late' then events[1](issued[3].request..'|ok');assert(session:state()=='failed') end
  end
 else
  now=1.3;assert(session:tick())
  assert(#reports==1 and reports[1].status=='estimated' and math.abs(reports[1].velocity.x-10)<1e-8)
  assert(issued[4].kind=='normal' and count('SAMPLE')==0)
  events[1](issued[4].request..'|ok')
  assert(count('SAMPLE')==1 and outgoing[#outgoing]:match('|1|1|sector_a|'))
  if mode=='late_active' then
   events[1](issued[2].request..'|ok');assert(session:state()=='failed')
  else
   assert(push('P|'..lease..'|'..attempt..'|STOP'..suffix..'|3'))
   assert(count('STOPPED')==1 and session:state()=='stopped')
   if mode=='late_stopped' then events[1](issued[3].request..'|ok');assert(session:state()=='failed') end
  end
 end
end
if mode~='ok' and mode~='delivery_ok' then assert(#faults>0)end
