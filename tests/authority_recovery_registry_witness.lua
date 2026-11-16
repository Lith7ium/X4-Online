local M=dofile('src/authority/lua/recovery_registry_witness.lua')
local nonce=string.rep('a',32);local epoch=string.rep('b',32)
local function make(phase)
 local now=1;local paused=true;local handler;local pending;local done=false;local errors={}
 local c={enabled=true,nonce=nonce,epoch=epoch,count=3,phase=phase,
  clock=function()return now end,paused=function()return paused end,
  register=function(f) handler=f;return true end,
  issue=function(screen,control,args) assert(screen=='X4AuthorityRegistryWitness');pending={control,args};return true end,
  fault=function(p,i,r)errors[#errors+1]={p,i,r} end,
  complete=function(e,n,p)assert(e==epoch and n==3 and p==phase);done=true;return true end}
 local api=M.new(c)
 local function reply(kind,i,status)
  local p=pending;pending=nil;assert(p)
  handler(nil,p[2].request_id..'|'..epoch..'|'..kind..'|'..i..'|'..(status or 'ok'))
 end
 return api,function() return pending end,reply,function()return done end,
  function(v)paused=v end,function(v)now=v end,errors
end
for _,phase in ipairs({'create','verify'}) do
 local api,pending,reply,done=make(phase)
 assert(api:start());assert(pending()[1]==(phase=='create' and 'Initialize' or 'BeginVerify'))
 reply(phase=='create' and 'init' or 'begin',0)
 for i=1,3 do assert(api:tick());assert(pending()[1]=='Step' and pending()[2].index==i);reply(phase,i) end
 assert(api:tick());assert(pending()[1]=='Finish');reply('finish',3)
 assert(done() and api:state()=='done')
end
local api,pending,reply,done,paused=make('verify')
assert(api:start());paused(false);assert(not pcall(reply,'begin',0));assert(api:state()=='failed' and not done())
api,pending,reply,done=make('create');assert(api:start());assert(not pcall(reply,'init',1));assert(api:state()=='failed' and not done())
local timed,_,_,_,_,time=make('create');assert(timed:start());time(31);assert(not timed:tick() and timed:state()=='failed')
local bad,_,response,_,_,_,errors=make('verify');assert(bad:start())
assert(not pcall(response,'begin',0,'refused'));assert(errors[1][1]=='verify' and errors[1][2]==0 and errors[1][3]=='refused')
local mismatch; mismatch,_,response,_,_,_,errors=make('create');assert(mismatch:start())
assert(not pcall(response,'init',2));assert(errors[1][3]=='event_mismatch')
local late;late,_,_,_,_,time,errors=make('create');assert(late:start());time(31)
assert(not late:tick());assert(errors[1][3]=='deadline')
local handler;local reentrant_errors={};local instant=M.new({enabled=true,phase='create',epoch=epoch,nonce=nonce,count=1,
 clock=function()return 1 end,paused=function()return true end,
 register=function(f)handler=f;return true end,
 issue=function(_,_,v)handler(nil,v.request_id..'|'..epoch..'|init|0|ok');return true end,
 complete=function()return true end,
 fault=function(p,i,r)reentrant_errors[#reentrant_errors+1]={p,i,r} end})
assert(not instant:start());assert(instant:state()=='failed')
assert(#reentrant_errors==1 and reentrant_errors[1][3]=='reentrant_event')
