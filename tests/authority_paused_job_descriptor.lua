local P=dofile('tools/dev/authority_paused_job_descriptor.lua');local Core=dofile('tools/dev/authority_job_descriptor_probe.lua')
assert(P.new({})==nil and P.new_x4({})==nil)
local epoch,rid=string.rep('a',32),string.rep('b',32)
local function rig(kind)
 local paused,game,t=true,10,1;local calls={};local app;local dcount=0
 local o={enabled=true,core=Core,epoch=epoch,request_id=rid,timeout=3,row={epoch=epoch,index=10055,sequence=2,classification='new_registry_entry'},actor={id='123'},
  clock=function()return t end,game_time=function()return game end,guard=function()return true end,paused=function()return paused end,
  docking=function()dcount=dcount+1;if kind=='docked' or (kind=='docked_after' and dcount==2) then return true,false,false elseif kind=='unknown' then return nil,false,false end;return false,false,false end,
  actor_key=function(a)return a.id end,hex_key=function(s)return s=='0x7b' and '123' or '44' end,
  snapshot=function()if kind=='unpause' then paused=false elseif kind=='game_changed' then game=11 elseif kind=='timeout' then t=4 elseif kind=='reentrant' then app:tick() end
   return {sector_local='44',x=kind=='nan' and 0/0 or 1,y=2,z=3,game_before=10,game_after=10} end,
  issue=function(screen,op,args)calls[#calls+1]={screen=screen,op=op,args=args};return true end}
 app=P.new(o);return app,calls
end
local result=rid..'|'..epoch..'|10055|ok|0x7b|ship_macro|argon|0x2c|sector_macro'
local p,calls=rig();assert(p:start() and calls[1].screen=='X4AuthorityPausedJobDescriptor');local ok,row=p:response(result)
assert(ok and row.x==1 and row.sector_local==nil and row.paused_checks_passed and not row.continuous_pause_proven and not row.docking_continuously_excluded and not row.descriptor_atomic)
for _,kind in ipairs({'docked','docked_after','unknown','unpause','game_changed','timeout','reentrant','nan'}) do
 local probe=rig(kind);assert(probe:start());assert(not probe:response(result),kind);assert(probe:state()=='failed',kind)
end
local fail=rig();assert(fail:start());assert(not fail:response(result:gsub('0x7b','0x01')))
print('paused job descriptor tests passed')
