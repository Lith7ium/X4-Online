local M=dofile('tools/dev/authority_player_flight_observer.lua');assert(M.new({enabled=false})==nil)
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local function rig(kind)
 local t,g,paused=1,3,true;local issued={};local app;local calls=0
 local o={enabled=true,epoch=epoch,nonce=nonce,timeout=20,
  guard=function()return t,g,paused end,confirmed=function()return kind~='unconfirmed' end,
  issue=function(s,op,a)issued[#issued+1]={s,op,a};if kind=='reentrant'then app:refused()end;return true end,
  inspect=function()calls=calls+1;if kind=='inspect_error'then error('secret')end;if kind=='slow'then t=21 end
   return {real_before=t,real_after=t,game_before=g,game_after=g,x=1,y=2,z=3,yaw=0,pitch=0,roll=0}
  end}
 app=M.new(o);return app,issued,function(v)t=v end,function(v)g=v end,function(v)paused=v end
end
local function row(i)return nonce..'|'..epoch..'|'..i..'|0xa|0xb|0xc|player'end
local a,issued,time,game,pause=rig();assert(a:arm());assert(a:begin_resume());pause(false);assert(a:tick());assert(a:state()=='await_running')
game(3.5);time(2);assert(a:tick() and a:state()=='ready')
for i,label in ipairs({'neutral','before','after'})do time(i+2);game(i+3);assert(a:request(label));local ok,r=a:response(row(i));assert(ok and r.sequence==i and r.label==label and not r.movement_cause_proven and not r.input_proven)end
assert(a:state()=='done' and a:close());assert(not a:response(row(3)) and a:state()=='failed')
local b=rig('unconfirmed');assert(not b:arm() and b:state()=='failed')
local c,_,_,_,pp=rig();assert(c:arm());pp(false);assert(not c:begin_resume())
local d,_,tt,gg,p=rig();assert(d:arm());assert(d:begin_resume());p(false);tt(2);gg(4);assert(d:tick());assert(d:request('neutral'));assert(not d:response(row(2)))
local e,_,te,ge,pe=rig('reentrant');assert(e:arm());assert(e:begin_resume());pe(false);te(2);ge(4);assert(e:tick());assert(not e:request('neutral'))
local f,_,tf,gf,pf=rig('slow');assert(f:arm());assert(f:begin_resume());pf(false);tf(2);gf(4);assert(f:tick());assert(f:request('neutral'));assert(not f:response(row(1)))
local h,_,th,gh,ph=rig();assert(h:arm());assert(h:begin_resume());ph(false);th(2);gh(4);assert(h:tick());assert(h:request('neutral'));assert(h:response(row(1)));assert(h:request('before'));assert(not h:response(row(2)))
local lost,_,tl,gl,pl=rig();assert(lost:arm());assert(lost:begin_resume());pl(false);tl(2);gl(4);assert(lost:tick());pl(true);assert(not lost:tick())
print('player flight observer state checks passed')
