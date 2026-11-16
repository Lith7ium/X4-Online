local M=dofile('tools/dev/authority_positive_seat_search.lua');assert(M.new({enabled=false})==nil)
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local function rig(kind)
 local t,game,paused=1,3,true;local issued={};local app
 local o={enabled=true,epoch=epoch,nonce=nonce,timeout=5,
  guard=function() assert(paused);return t,game end,
  issue=function(screen,op,args) issued[#issued+1]={screen,op,args};if kind=='reentrant' then app:refused() end;return true end,
  inspect=function() if kind=='error' then error('private values') end;if kind=='slow' then t=6 end;if kind=='missing' then return 'missing' end;return 'present' end}
 app=M.new(o);return app,issued,function(v)t=v end,function(v)paused=v end,function(v)game=v end
end
local msg=nonce..'|'..epoch..'|0xa|0xb|0xc|occupied'
local p,i=rig();assert(p:start());assert(#i==1 and i[1][2]=='Read');local ok,res=p:response(msg)
assert(ok and res.status=='candidate_observed' and not res.same_actor_proven and not res.player_control_proven)
assert(not p:response(msg) and p:state()=='failed')
for _,kind in ipairs({'error','missing'}) do local a=rig(kind);assert(a:start());local ok,r=a:response(msg);assert(ok and r.status=='inconclusive') end
local a=rig();assert(a:start());local ok,r=a:inconclusive(nonce..'|'..epoch..'|inconclusive');assert(ok and r.status=='inconclusive' and r.reason=='search_inconclusive')
a=rig();assert(a:start());assert(not a:response(msg:gsub('^b','c')) and a:state()=='failed')
a=rig();assert(a:start());assert(not a:response(msg:gsub('occupied','empty')) and a:state()=='failed')
a=rig('reentrant');assert(not a:start() and a:state()=='failed')
a=rig('slow');assert(a:start());assert(not a:response(msg) and a:state()=='failed')
local x,_,clock=rig();assert(x:start());clock(6);ok,r=x:tick();assert(ok and r.status=='inconclusive' and r.reason=='timeout');assert(not x:response(msg))
local y,_,_,pause=rig();assert(y:start());pause(false);assert(not y:tick() and y:state()=='failed')
local z,_,_,_,game=rig();assert(z:start());game(4);assert(not z:response(msg) and z:state()=='failed')
print('positive-seat search state checks passed')
