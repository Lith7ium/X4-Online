local M=dofile('tools/dev/authority_player_control_once.lua');assert(M.new({enabled=false})==nil)
local epoch,nonce=string.rep('a',32),string.rep('b',32);local request={}
local function rig(which)
 local t,g,paused=1,3,true;local app;local issued={};local calls={};local inspections=0
 local o={enabled=true,epoch=epoch,nonce=nonce,timeout=10,
  guard=function(mode)assert(paused);calls[#calls+1]=mode;return t,(which=='jump' and mode=='post') and g+1 or g end,
  issue=function(s,op,a)issued[#issued+1]={s,op,a};if which=='reentrant' then app:refused() end;return true end,
  validate=function()if which=='slow_validate' then t=11 end;return which~='invalid' end,inspect=function(_,_,flags) inspections=inspections+1;if which=='slow_final' and inspections==3 then t=11 end;if which=='inspect_error' then error('secret') end;return true end}
 app=M.new(o);return app,issued,calls,function(x)t=x end,function(x)paused=x end,function(x)g=x end
end
local created=nonce..'|'..epoch..'|0xa|0xb'
local function row(seq,p,o,c,s,owner)return nonce..'|'..epoch..'|'..seq..'|0xa|0xb|'..p..'|'..o..'|'..c..'|'..s..'|1|'..(owner or 'player')end
local function ready(which)
 local a,i,c=rig(which);assert(a:tick());assert(a:created(created));assert(a:tick());assert(a:response(row(0,0,0,0,1)));return a,i,c
end
local a,i,c=ready();assert(a:tick());assert(i[#i][2]=='Teleport');assert(a:dispatched(nonce..'|'..epoch));assert(a:tick());assert(a:response(row(1,1,1,1,1)));assert(a:tick());local ok,r=a:response(row(2,1,1,1,1))
assert(ok and r.status=='controlled' and r.local_control_proven and not r.seat_free_proven and not r.flight_proven)
assert(a:state()=='done');assert(not a:response(row(2,1,1,1,1)));assert(a:state()=='failed')
local pre,post=false,false;for _,v in ipairs(c)do if v=='pre'then pre=true elseif v=='post'then post=true end end;assert(pre and post)
local b=ready();assert(b:tick());assert(b:dispatched(nonce..'|'..epoch));assert(b:tick());ok,r=b:response(row(1,0,0,0,0));assert(ok and r.status=='inconclusive' and not r.local_control_proven)
local d=ready();assert(d:tick());assert(not d:tick() or d:state()=='dispatching');assert(not d:dispatched('bad'))
local x,_,_,clock=rig();assert(x:tick());clock(11);ok,r=x:tick();assert(ok and r.status=='inconclusive' and x:state()=='done');assert(not x:created(created))
local y,_,_,_,pause=rig();assert(y:tick());pause(false);assert(not y:created(created) and y:state()=='failed')
local z=rig('reentrant');assert(not z:tick() and z:state()=='failed')
local q=rig('invalid');assert(q:tick());assert(not q:created(created))
local v=rig('inspect_error');assert(v:tick());assert(v:created(created));assert(v:tick());assert(not v:response(row(0,0,0,0,1)))
print('player-control state tests passed')

local slow=ready('slow_final');assert(slow:tick());assert(slow:dispatched(nonce..'|'..epoch));assert(slow:tick());assert(slow:response(row(1,1,1,1,1)));assert(slow:tick());local checked,late=slow:response(row(2,1,1,1,1));assert(checked and late.status=='inconclusive' and not late.local_control_proven)
local overdue,_,_,advance=rig();assert(overdue:tick());advance(11);assert(not overdue:created(created) and overdue:state()=='failed')
local sv=rig('slow_validate');assert(sv:tick());local vok,vr=sv:created(created);assert(vok and vr.status=='inconclusive' and not vr.local_control_proven);assert(not sv:created(created))
local jump,ij=ready('jump');assert(not jump:tick() and jump:state()=='failed');assert(ij[#ij][2]~='Teleport')
