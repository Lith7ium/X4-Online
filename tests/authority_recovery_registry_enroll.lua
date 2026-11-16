local M=dofile('src/authority/lua/recovery_registry_enroll.lua')
local registry=dofile('src/authority/lua/ship_registry_client.lua')
local function fixture()
 local sent,done={},{};local t=1;local paused=true
 local opts={enabled=true,epoch=string.rep('a',32),nonce=string.rep('b',32),limit=3,registry=registry,
  clock=function()return t end,paused=function()return paused end,
  issue=function(screen,op,args)sent[#sent+1]={screen=screen,op=op,args=args};return true end,
  key=function(v)return tostring(v)end,valid=function(v)return v=='1' or v=='2' end,
  to_md_actor=function(v)return v end,from_md_actor=function(v)return tostring(tonumber(v))end,
  candidates=function()return 'done',{'1','2'}end,
  complete=function(epoch,n)done[#done+1]={epoch,n};return true end}
 return M.new(opts),sent,done,function(x)paused=x end,function(x)t=x end
end
local function respond(owner,sent,payload)
 local msg=sent[#sent];assert(msg);assert(owner:event(msg.args.request_id..'|'..payload))
end
local owner,sent,done=fixture();assert(owner:start());assert(sent[1].op=='Status')
respond(owner,sent,'Uninitialized|');assert(owner:tick() and sent[2].op=='Initialize')
respond(owner,sent,'Initialized|'..string.rep('a',32));assert(owner:tick())
for i=1,2 do
 assert(sent[#sent].op=='Enroll');respond(owner,sent,'Enrolled|'..i);assert(owner:tick())
 assert(sent[#sent].op=='Resolve');respond(owner,sent,'Actor|0x'..i);assert(owner:tick())
 assert(sent[#sent].op=='Enroll');respond(owner,sent,'Enrolled|'..i);assert(owner:tick())
end
assert(owner:state()=='done' and done[1][2]==2)
-- Existing, ambiguous, stale, timed out or unpaused status never initializes.
for _,reply in ipairs({'Epoch|'..string.rep('a',32),'Faulted|','Uninitialized|extra'}) do
 local o,s=fixture();assert(o:start());assert(not o:event(s[1].args.request_id..'|'..reply));assert(o:state()=='failed' and #s==1)
end
local o,s,_,setpause=fixture();assert(o:start());setpause(false);assert(not o:tick() and #s==1)
local p,ps,_,_,settime=fixture();assert(p:start());settime(31);assert(not p:tick() and #ps==1)
local q,qs=fixture();assert(q:start());assert(not q:event(string.rep('c',32)..':0|Uninitialized|') and #qs==1)
print('recovery registry enrollment checks passed')
