local W=dofile('tools/dev/authority_census_replica_udp.lua');local Base=dofile('tools/dev/authority_census_job_owner.lua')
assert(W.new({})==nil)
local lease,attempt,epoch,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32)
local function rig(opt)
 opt=opt or {};local inbox,outbox,logs,rlogs={},{},{},{};local n=1;local base,w
 local net={send=function(_,v)outbox[#outbox+1]=v;return true end,receive=function()return table.remove(inbox,1)end,close=function()return true end}
 local function guard()return not opt.bad_guard end
 local function factory(proxy,log)
  base=assert(Base.new({enabled=true,role='client',epoch=epoch,attempt=attempt,nonce=nonce,lease=lease,timeout=60,window=30,net=proxy,clock=function()return n end,
   guard=guard,observe=function()return true,10 end,pause=function()end,resume=function()end,baseline_request=function()return true end,
   host_factory=function()error('unexpected')end,descriptor_factory=function()error('unexpected')end,
   witness_factory=function(i,m)return {start=function()return true end,tick=function()return true end,close=function()return true end,
    response=function()return true,{epoch=epoch,index=i,sector_macro=m,local_witness_match=true}end}end,log=log}))
  return base
 end
 local replica={start=function(_,d,witness)assert(d.job_sequence==2 and d.x==1 and witness.index==41);return not opt.start_fail end,
  tick=function()if opt.tick_fail then return false end;if opt.after_guard_fail then opt.bad_guard=true end;return true,'intent_ready'end,
  take_intent=function()return true,{attempt=attempt,epoch=epoch,transport_sequence=1,job_sequence=2,index=10055}end}
 w=assert(W.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,timeout=60,net=net,clock=function()return n end,guard=guard,
  log=function(s)logs[#logs+1]=s end,replica_log=function(s)rlogs[#rlogs+1]=s end,base_factory=factory,replica_factory=function()return replica end}))
 local cmd=table.concat({'CMD',lease,'client',attempt,epoch},'|')
 return w,inbox,outbox,logs,rlogs,cmd,opt
end
local w,i,o,l,r,p=rig();assert(w:tick());assert(w:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(w:tick())
i[1]=p..'|WITNESS|2|41|sector_a';assert(w:tick());assert(w:witness_event('ignored'));assert(w:tick());assert(l[#l]=='WITNESS_READY' and o[#o]:match('|WITNESS_READY|2|41|sector_a$'))
for _,v in ipairs(o)do assert(not v:match('|WITNESS_OK|'))end
i[1]=p..'|REPLICA|2|10055|ship_a|argon|sector_a|1|2|3';assert(w:tick() and w:state()=='intent_pending')
assert(w:tick() and w:state()=='finished' and l[#l]=='WITNESS_OK' and r[#r]=='DONE');assert(o[#o]:match('|WITNESS_OK|2|41|sector_a$'));assert(w:tick());assert(w:close())
for _,kind in ipairs({'start_fail','tick_fail','after_guard_fail'})do
 local x,xi,xo,xl,xr,xp=rig({[kind]=true});assert(x:tick());assert(x:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(x:tick());xi[1]=xp..'|WITNESS|2|41|sector_a';assert(x:tick());assert(x:witness_event('ignored'));assert(x:tick());xi[1]=xp..'|REPLICA|2|10055|ship_a|argon|sector_a|1|2|3';assert(not x:tick() and x:state()=='failed');for _,v in ipairs(xo)do assert(not v:match('|WITNESS_OK|'))end
end
local x,xi,xo,xl,xr,xp=rig();assert(x:tick());assert(x:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(x:tick());xi[1]=xp..'|REPLICA|2|10055|ship_a|argon|sector_a|1|2|3';assert(not x:tick())
print('replica UDP owner tests passed')
