-- Synthetic callbacks only; no X4 or network.
local M=dofile('tools/dev/authority_job_descriptor_probe.lua')
assert(M.new({enabled=false})==nil and M.new_x4({enabled=false})==nil)
local epoch,rid=string.rep('a',32),string.rep('b',32)
local function rig(kind)
 local t,game,live=0,10,true;local requests={};local app;local guards=0
 local row={epoch=epoch,index=10055,sequence=1,classification='new_registry_entry'}
 local o={enabled=true,epoch=epoch,request_id=rid,timeout=3,row=row,actor={key='123'},
  clock=function() return t end,game_time=function() if kind=='slow_start' then t=4 end;return game end,
  guard=function() guards=guards+1;if kind=='slow_guard' and guards==2 then t=4 end;return live end,
  actor_key=function(a) return a.key end,
  hex_key=function(v) if v=='0x7b' then return '123' elseif v=='0x2c' then return '44' else return '456' end end,
  snapshot=function(actor,sector)
   if kind=='timeout_snapshot' then t=4 end
   if kind=='reentrant' then app:tick() end
   if kind=='lost_sector' then error('sector changed') end
   return {sector_local='44',x=(kind=='nan' and 0/0 or 1),y=2,z=3,
           game_before=(kind=='reverse_time' and 9 or 10),game_after=11}
  end,
  issue=function(screen,operation,args) requests[#requests+1]={screen=screen,operation=operation,args=args};return true end}
 app=M.new(o)
 return app,requests,function(v) t=v end,function(v) live=v end
end
local function row(actor,index,owner,request)
 return (request or rid)..'|'..epoch..'|'..(index or '10055')..'|ok|'..(actor or '0x7b')..'|ship_arg_s_fighter_01_a_macro|'..(owner or 'argon')..'|0x2c|sector_a_macro'
end
local app,requests=rig();assert(app:start());assert(#requests==1 and requests[1].args.index==10055)
local ok,result=app:response(row());assert(ok and app:state()=='done')
assert(result.macro=='ship_arg_s_fighter_01_a_macro' and result.owner=='argon' and result.sector_local==nil)
assert(result.x==1 and result.game_before_request==10 and result.game_after_pose==11)
assert(not result.descriptor_atomic and not result.birth_confirmed and not result.delivery_confirmed)
for _,kind in ipairs({'timeout_snapshot','reentrant','lost_sector','nan','reverse_time'}) do
 local p=rig(kind);assert(p:start());assert(not p:response(row()));assert(p:state()=='failed',kind)
end
local slow,sent=rig('slow_start');assert(not slow:start());assert(#sent==0 and slow:state()=='failed')
local slow_guard,not_sent=rig('slow_guard');assert(not slow_guard:start());assert(#not_sent==0 and slow_guard:state()=='failed')
for _,bad in ipairs({row('0x88'),row(nil,'10056'),row(nil,nil,'bad|owner'),row(nil,nil,nil,string.rep('c',32)),
 rid..'|'..epoch..'|10055|unavailable'}) do
 local p=rig();assert(p:start());assert(not p:response(bad));assert(p:state()=='failed')
end
local p,_,clock=rig();assert(p:start());clock(3);assert(not p:tick());assert(p:state()=='failed')
local lost,_,_,guard=rig();assert(lost:start());guard(false);assert(not lost:tick());assert(lost:state()=='failed')
local function invalid(changes)
 local opts={enabled=true,epoch=epoch,request_id=rid,timeout=3,actor=1,
 row={epoch=epoch,index=1,sequence=1,classification='new_registry_entry'},
 issue=function() end,clock=function() end,game_time=function() end,guard=function() end,
 actor_key=function() end,hex_key=function() end,snapshot=function() end}
 for key,value in pairs(changes) do opts[key]=value end
 assert(not pcall(M.new,opts))
end
invalid({row={epoch=epoch,index=1,sequence=1,classification='previously_observed'}})
invalid({request_id='bad'})
print('job descriptor synthetic checks passed')
