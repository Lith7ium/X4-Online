local M=dofile('tools/dev/authority_census_replica_client.lua');assert(M.new({})==nil)
local epoch,attempt,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32)
local desc={version=1,type='job_descriptor',attempt=attempt,epoch=epoch,transport_sequence=1,job_sequence=7,index=10055,macro='ship_a',faction='argon',sector_macro='sector_a',x=1,y=2,z=3}
local witness={epoch=epoch,index=41,sector_macro='sector_a',local_witness_match=true}
local function rig(opt)
 opt=opt or {};local now,game=1,20;local count=4;local reqs={};local app;local samples=0
 local o={enabled=true,epoch=epoch,attempt=attempt,nonce=nonce,timeout=5,clock=function()return now end,
  guard=function()return not opt.guard_fail,game end,release_guard=function()if opt.late_release then now=9 end;if opt.reentrant then app:tick() end;return not opt.release_fail end,
  count=function()return count end,issue=function(screen,op,args)reqs[#reqs+1]={screen=screen,op=op,args=args};if op=='Create' then count=5 end;return not opt.issue_fail end,
  snapshot=function()samples=samples+1;if opt.slow then now=9 end;return {actor_key=opt.actor_change and samples==2 and '11' or '10',sector_key=opt.sector_change and samples==2 and '4' or '2',x=opt.x or 1,y=2,z=3}end}
 app=M.new(o);return app,reqs
end
local function inspect(app,step)
 assert(app:event('X4AuthorityCensusReplica.Created',10055));return app:event('X4AuthorityCensusReplica.Inspection',nonce..'-'..step..'|'..epoch..'|10055|0xa|0x2|sector_a')
end
local a,req=rig();assert(a:start(desc,witness));assert(a:event('X4AuthorityCensusReplica.Initialized',epoch));assert(inspect(a,1));assert(inspect(a,2));assert(a:state()=='intent_pending');assert(not a:take_intent());assert(a:state()=='failed')
local b,breq=rig();assert(b:start(desc,witness));assert(b:event('X4AuthorityCensusReplica.Initialized',epoch));assert(inspect(b,1));assert(inspect(b,2));assert(b:tick());local ok,intent=b:take_intent();assert(ok and intent.job_sequence==7 and intent.index==10055 and intent.actor==nil)
assert(breq[2].args.x==breq[4].args.x and breq[2].args.witness_index==41 and breq[4].args.witness_index==41)
for _,mode in ipairs({'actor_change','sector_change','slow'})do local p=rig({[mode]=true});assert(p:start(desc,witness));assert(p:event('X4AuthorityCensusReplica.Initialized',epoch));if mode=='slow' then assert(not inspect(p,1)) else assert(inspect(p,1));assert(not inspect(p,2))end;assert(p:state()=='failed')end
local bad,badreq=rig({x=3.01});assert(bad:start(desc,witness));assert(bad:event('X4AuthorityCensusReplica.Initialized',epoch));assert(not inspect(bad,1));assert(#badreq==3 and bad:state()=='failed');assert(not bad:tick() and #badreq==3)
local edge=rig({x=3});assert(edge:start(desc,witness));assert(edge:event('X4AuthorityCensusReplica.Initialized',epoch));assert(inspect(edge,1) and inspect(edge,2))
for _,mode in ipairs({'release_fail','late_release','reentrant'})do local p=rig({[mode]=true});assert(p:start(desc,witness));assert(p:event('X4AuthorityCensusReplica.Initialized',epoch));assert(inspect(p,1) and inspect(p,2) and p:tick());assert(not p:take_intent());assert(p:state()=='failed')end
local extra={};for k,v in pairs(desc)do extra[k]=v end;extra.actor='0x1';local p=rig();assert(not p:start(extra,witness))
local w={epoch=epoch,index=41,sector_macro='other',local_witness_match=true};p=rig();assert(not p:start(desc,w))
print('census replica client state tests passed')
