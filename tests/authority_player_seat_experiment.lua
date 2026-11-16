local M=dofile('tools/dev/authority_player_seat_experiment.lua')
assert(M.new({enabled=false})==nil)
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local function rig(kind)
 local t,game,paused=1,3,true;local issued,logs={},{};local app;local count=0
 local seat={}
 function seat:start() return true end
 function seat:tick() return true end
 function seat:state() return count==3 and 'done' or 'waiting' end
 function seat:response()
  count=count+1
  if kind=='seat_error' then return false end
  if count~=3 then return true end
  local r={{actor_key='10',sector_key='20',assigned='present',reservation='occupied'},
           {actor_key='11',sector_key='21',assigned='nil_observed',reservation='empty'},
           {actor_key='12',sector_key='20',assigned='nil_observed',reservation='empty'}}
  if kind=='wrong_actor' then r[1].actor_key='9' end
  if kind=='occupied' then r[2].reservation='occupied' end
  return true,{classification='inconclusive',positive_control_observed=true,rows=r,
   seat_free_proven=false,player_control_proven=false,save_authorized=false}
 end
 local o={enabled=true,epoch=epoch,nonce=nonce,timeout=10,
  guard=function() assert(paused);return t,game,'10','20' end,
  issue=function(screen,op,args) issued[#issued+1]={screen,op,args};if kind=='reenter' then app:created(2) end;if kind=='postguard' and op=='Create' then paused=false end;return true end,
  make_seat=function() if kind=='construct_error' then error('secret exception') end;return seat end, live=function() return kind~='lost_actor' end, log=function(x) logs[#logs+1]=x end}
 app=M.new(o)
 return app,issued,logs,function(x)t=x end,function(x)paused=x end,function(x)game=x end
end
local function prepare(kind)
 local a,i,l,clock,pause,game=rig(kind);assert(a:tick());assert(a:preflight(nonce..'|'..epoch..'|ok'))
 assert(a:tick());assert(a:created(2));assert(a:tick());return a,i,l,clock,pause,game
end
local a,i,l=prepare();assert(#i==2 and i[2][2]=='Create');assert(a:response('x'));assert(a:response('y'));assert(a:response('z'))
assert(a:tick() and a:state()=='done');assert(table.concat(l,',')=='PREFLIGHT,CREATED,POSITIVE,NEGATIVE1,NEGATIVE2,DONE')
assert(a:tick());assert(not a:created(2) and a:state()=='failed');assert(l[#l]=='ERROR CREATED_RESULT')
for _,kind in ipairs({'wrong_actor','occupied','seat_error'}) do
 local p=prepare(kind)
 if kind=='seat_error' then assert(not p:response('x')) else assert(p:response('x'));assert(p:response('y'));assert(p:response('z'));assert(not p:tick()) end
 assert(p:state()=='failed')
end
local p=rig();assert(p:tick());assert(not p:preflight('bad'));assert(p:state()=='failed')
p=rig();assert(p:tick());assert(not p:created(2));assert(p:state()=='failed')
p=rig('reenter');assert(not p:tick());assert(p:state()=='failed')
local vanished=prepare('lost_actor');assert(vanished:response('x'));assert(vanished:response('y'));assert(not vanished:response('z'));assert(vanished:state()=='failed')
local timed,_,_,clock=rig();assert(timed:tick());clock(11);assert(not timed:tick());assert(timed:state()=='failed')
local lost,_,_,_,pause=prepare();pause(false);assert(not lost:tick());assert(lost:state()=='failed')
local moving,_,_,_,_,game=prepare();game(4);assert(not moving:tick());assert(moving:state()=='failed')
print('player seat experiment synthetic checks passed')

local ctor,_,ctorlog=rig('construct_error');assert(ctor:tick());assert(ctor:preflight(nonce..'|'..epoch..'|ok'))
assert(ctor:tick());assert(ctor:created(2));assert(not ctor:tick());assert(ctorlog[#ctorlog]=='ERROR SEAT_CONSTRUCT')
assert(not table.concat(ctorlog):find('secret',1,true))
local pg,_,pglog=rig('postguard');assert(pg:tick());assert(pg:preflight(nonce..'|'..epoch..'|ok'));assert(not pg:tick());assert(pglog[#pglog]=='ERROR POST_GUARD')
local refusal,_,refusallog=rig();assert(refusal:tick());assert(not refusal:refused('seat'));assert(refusallog[#refusallog]=='ERROR SEAT_REFUSED')
