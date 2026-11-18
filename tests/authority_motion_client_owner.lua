local core=dofile('src/authority/lua/motion_client_owner.lua')
local net={send=function()return true end,receive=function()return nil end}
local c={enabled=true,lease=('a'):rep(32),attempt=('b'):rep(32),epoch=('c'):rep(32),generation=('d'):rep(32),nonce=('e'):rep(32),
 timeout=1,max_age=1,max_tracks=10,clock=function()return 1 end,guard=function()return true end,
 buffer={new=function()return {push=function()return true end}end},register=function()return true end,factory=function()return {} end,fault=function()end,net=net}
local owner=assert(core.new(c));assert(not pcall(core.new,c))
assert(owner:start());assert(owner:tick())
print('exclusive motion IPC owner checks passed')
-- A defective injected buffer cannot mutate the sample and still receive BOUND.
for _,mode in ipairs({'value','pose_field','pose_meta','sample_field','sample_meta','rate_field','rate_meta'})do
 local q,out={},{};local cb
 local socket={send=function(_,s)out[#out+1]=s;return true end,receive=function()return table.remove(q,1)end}
 local x=assert(core.new({enabled=true,lease=('a'):rep(32),attempt=('b'):rep(32),epoch=('c'):rep(32),generation=('d'):rep(32),nonce=('e'):rep(32),
  timeout=2,max_age=2,max_tracks=10,clock=function()return 1 end,guard=function()return true end,net=socket,fault=function()end,
  register=function(f)cb=f;return true end,
  buffer={new=function()return {push=function(_,sample)
   if mode=='value' then sample.pose[1]=9
   elseif mode=='pose_field' then sample.pose.extra=9
   elseif mode=='pose_meta' then setmetatable(sample.pose,{})
   elseif mode=='sample_field' then sample.extra=9
   elseif mode=='sample_meta' then setmetatable(sample,{})
   elseif mode=='rate_field' then sample.rate.extra=9
   elseif mode=='rate_meta' then setmetatable(sample.rate,{}) end
   return true
  end}end},
  factory=function(opt)return {begin=function()return true end,tick=function()return true end,
   event=function()assert(opt.complete({epoch=opt.epoch,generation=opt.generation,index=opt.index,sequence=1,sector_macro=opt.sector_macro}));return true end}end}))
 assert(x:start());q[1]=table.concat({'M',('a'):rep(32),('b'):rep(32),'BIND',('f'):rep(32),('c'):rep(32),('d'):rep(32),'42','1','sector_a',('1'):rep(64),'10','1','2','3','4','5','6'},'|')
 assert(x:tick());cb(nil,'correlated');assert(x:state()=='failed' and #out==1)
end

-- BIND3 keeps game time separate from capture time and pins the track version.
local function v3_rig(mutate)
 local input,output,snapshots={}, {}, {};local callback;local begins=0;local options_seen
 local owner=assert(core.new({enabled=true,lease=('a'):rep(32),attempt=('b'):rep(32),epoch=('c'):rep(32),generation=('d'):rep(32),nonce=('e'):rep(32),
  timeout=2,max_age=2,max_tracks=10,clock=function()return 1 end,guard=function()return true end,fault=function()end,
  net={send=function(_,value)output[#output+1]=value;return true end,receive=function()return table.remove(input,1)end},
  register=function(fn)callback=fn;return true end,
  buffer={new=function(options)options_seen=options;return {push=function(_,sample,arrival)
   snapshots[#snapshots+1]={version=sample.version,game=sample.source_time,capture=sample.capture_time,rate=sample.real_rate,arrival=arrival}
   if mutate=='capture' then sample.capture_time=99 elseif mutate=='version' then sample.version=1
   elseif mutate=='rate' then sample.real_rate[1]=99 elseif mutate=='extra' then sample.rate={} end
   return true
  end}end},
  factory=function(options)
   local seq
   return {begin=function(_,request)begins=begins+1;seq=request.sequence;return true end,tick=function()return true end,
    event=function()assert(options.complete({epoch=options.epoch,generation=options.generation,index=options.index,sequence=seq,sector_macro=options.sector_macro}));return true end}
  end}))
 assert(owner:start())
 local function send(seq,game,capture,kind)
  local fields={'M',('a'):rep(32),('b'):rep(32),kind or 'BIND3',('f'):rep(32),('c'):rep(32),('d'):rep(32),'42',tostring(seq),'sector_a',('1'):rep(64),tostring(game)}
  if kind~='BIND' then fields[#fields+1]=tostring(capture) end
  for _,v in ipairs({'1','2','3','4','5','6'})do fields[#fields+1]=v end
  input[1]=table.concat(fields,'|');return owner:tick()
 end
 return owner,send,function()callback(nil,'correlated')end,snapshots,function()return begins end,function()return options_seen end,output
end
do
 local owner,send,complete,samples,_,options,output=v3_rig()
 assert(send(1,10,20));complete();assert(owner:state()=='ready')
 assert(options().clock_basis=='capture_time' and samples[1].version==3 and samples[1].game==10 and samples[1].capture==20 and samples[1].rate[1]==4 and samples[1].arrival==1)
 assert(send(2,10,21));complete();assert(owner:state()=='ready' and #output==3 and samples[2].capture==21)
end
for _,mode in ipairs({'capture','version','rate','extra'})do
 local owner,send,complete=v3_rig(mode);assert(send(1,10,20));complete();assert(owner:state()=='failed')
end
for _,values in ipairs({{2,9,21,'BIND3'},{2,10,20,'BIND3'},{2,10,19,'BIND3'},{2,11,21,'BIND'}})do
 local owner,send,complete,_,begins=v3_rig();assert(send(1,10,20));complete()
 assert(not send(unpack(values)) and owner:state()=='failed' and begins()==1)
end
