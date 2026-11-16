local M=dofile('tools/dev/authority_player_flight_live_owner.lua')
assert(M.new{}==nil)
local mode=arg[1] or 'normal';local t,g,paused=1,3,true;local resumed=0;local logs={};local phase='new';local n=0;local app
local fake={}
function fake:arm()assert(paused);phase='armed';return true end
function fake:begin_resume()assert(paused);phase='await_running';return true end
function fake:tick()
 if t>=20 then return false end
 if (phase=='ready' or phase=='waiting' or phase=='done') and paused then return false end
 if phase=='await_running' and not paused and g>3 then phase='ready' end
 return true
end
function fake:state()return phase end
function fake:request()phase='waiting';return true end
function fake:response()
 n=n+1;phase=n==3 and 'done' or 'ready'
 return true,{sequence=n,label=({'neutral','before','after'})[n],real_before=t,real_after=t,game_before=g,game_after=g,x=n,y=0,z=0,yaw=0,pitch=0,roll=0}
end
app=M.new{enabled=true,control_tick=function()return true end,control_state=function()return 'done'end,
 control_outcome=function()return mode=='inconclusive' and 'inconclusive' or 'controlled'end,
 handoff=function()return {}end,make=function()return fake end,
 resume=function()resumed=resumed+1;paused=false;return true end,is_paused=function()return paused end,
 clock=function()return t,g end,log=function(s)
  logs[#logs+1]=s
  if s=='RESUME_INTENT' then
   if mode=='slow' then t=20 elseif mode=='pause_lost' then paused=false
   elseif mode=='reentrant' then assert(not app:tick()) end
  end
  if s:match('^SAMPLE ') then
   if mode=='slow_sample' then t=20 elseif mode=='pause_sample' then paused=true end
  end
  if s=='DONE' then
   if mode=='slow_done' then t=20 elseif mode=='pause_done' then paused=true end
  end
 end}
assert(app:tick())
if mode=='inconclusive' then assert(app:tick());assert(app:state()=='inconclusive_done' and resumed==0);return end
if mode=='slow' or mode=='pause_lost' or mode=='reentrant' then
 assert(not app:tick());assert(resumed==0 and app:state()=='failed');return
end
assert(app:tick() and resumed==1);g=4;t=2;assert(app:tick());assert(app:tick())
if mode=='slow_sample' or mode=='pause_sample' then assert(not app:response('one') and app:state()=='failed');return end
assert(app:response('one'))
g=5;t=3;assert(app:tick());assert(app:response('two'))
g=6;t=4;assert(app:tick());assert(app:response('three'))
if mode=='slow_done' or mode=='pause_done' then
 assert(not app:tick() and app:state()=='failed');for _,s in ipairs(logs)do assert(s~='FENCED')end;return
end
assert(app:tick() and app:state()=='done')
assert(not app:response('late') and app:state()=='failed');print('flight owner checks passed')
