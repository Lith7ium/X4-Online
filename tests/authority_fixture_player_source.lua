local source=dofile('tools/dev/authority_fixture_player_source.lua')
local function setup(latest)
 local incoming={};local sent={};local paused=false;local seated=false;local idle=true;local pending=false;local starts=0;local ticks=0
 local resumes=0
 local net={send=function(_,v) sent[#sent+1]=v;return true end,
  receive=function() return table.remove(incoming,1) end,pending=function() return pending end}
 local session={start=function() starts=starts+1;return true end,
  tick=function() ticks=ticks+1;return true end,quiescent=function() return idle end,
  after_resume=function() resumes=resumes+1;return true end}
 local owner=source.new{net=net,lease='a',attempt='b',epoch='c',generation='d',
  latest_cache=latest,
  seat_ready=function() return seated end,paused=function() return paused end,guard=function() return true end,
  make_session=function() return session end,fault=function() end}
 return owner,incoming,sent,function(v)seated=v end,function(v)paused=v end,
  function(v)idle=v end,function(v)pending=v end,function()return starts,ticks,resumes end
end
local owner,incoming,sent,seat,pause,idle,pending,counts=setup()
assert(owner:tick() and #sent==0);seat(true);assert(owner:tick() and sent[1]=='READY|a|b|c|d')
assert(owner:tick() and #sent==1);incoming[1]='ARM|a|b|c|d';assert(owner:tick())
local starts,ticks=counts();assert(starts==1 and ticks==0)
assert(owner:tick());pause(true);assert(owner:tick());assert(owner:tick());pause(false);assert(owner:tick())
starts,ticks=counts();assert(starts==1 and ticks==2)
pause(true);idle(false);assert(not owner:tick() and owner:state()=='failed')
local b,packets,_,sit,pa=setup();sit(true);assert(b:tick());pa(true);packets[1]='ARM|a|b|c|d';assert(not b:tick())
local c,p2,_,sit2,pa2,_,pend2=setup();sit2(true);assert(c:tick());p2[1]='ARM|a|b|c|d';assert(c:tick());pa2(true);pend2(true);assert(not c:tick())
local d,p3,_,sit3=setup();sit3(true);assert(d:tick());p3[1]='ARM|wrong';assert(not d:tick())
local e,p4,_,sit4,pa4,_,_,count4=setup(true)
sit4(true);assert(e:tick());p4[1]='ARM|a|b|c|d';assert(e:tick())
pa4(true);assert(e:tick());assert(e:tick());pa4(false);assert(e:tick())
local _,_,resumes=count4();assert(resumes==1)
local f,p5,_,sit5,pa5,idle5=setup(true)
sit5(true);assert(f:tick());p5[1]='ARM|a|b|c|d';assert(f:tick())
idle5(false);pa5(true);assert(not f:tick() and f:state()=='failed')
local g,p6,_,sit6,pa6,_,pend6=setup(true)
sit6(true);assert(g:tick());p6[1]='ARM|a|b|c|d';assert(g:tick())
pa6(true);assert(g:tick());pend6(true);pa6(false);assert(not g:tick() and g:state()=='failed')
print('fixture player source lifecycle passed')
