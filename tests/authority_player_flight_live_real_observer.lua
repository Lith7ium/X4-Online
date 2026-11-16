local Flight=dofile('tools/dev/authority_player_flight_observer.lua')
local Owner=dofile('tools/dev/authority_player_flight_live_owner.lua')
local epoch,nonce=string.rep('a',32),string.rep('b',32);local paused=true;local t,g=1,3;local pending;local events={}
local observer=Flight.new{enabled=true,epoch=epoch,nonce=nonce,timeout=20,confirmed=function()return true end,
 guard=function()return t,g,paused end,
 issue=function(_,_,args)assert(not pending);pending=args.seq;return true end,
 inspect=function()return {real_before=t,real_after=t,game_before=g,game_after=g,x=1,y=2,z=3,yaw=4,pitch=5,roll=6}end}
local app=Owner.new{enabled=true,control_tick=function()return true end,control_state=function()return 'done'end,
 control_outcome=function()return 'controlled'end,handoff=function()return {}end,make=function()return observer end,
 resume=function()paused=false;return true end,is_paused=function()return paused end,clock=function()return t,g end,
 log=function(s)events[#events+1]=s end}
assert(app:tick());assert(app:tick());t=2;g=4;assert(app:tick())
for i=1,3 do
 t=i+2;g=i+4;assert(app:tick());assert(pending==i);pending=nil
 assert(app:response(nonce..'|'..epoch..'|'..i..'|0x1|0x2|0x3|player'))
end
assert(app:tick() and app:state()=='done');assert(#events==9 and events[9]=='FENCED')
assert(not app:response(nonce..'|'..epoch..'|3|0x1|0x2|0x3|player'))
