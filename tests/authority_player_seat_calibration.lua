-- Synthetic event/FFI boundary only; does not execute X4.
local M=dofile('tools/dev/authority_player_seat_calibration.lua')
assert(M.new({enabled=false})==nil)
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local function rig(change)
 local t,paused=0,true;local issued={};local app
 local o={enabled=true,epoch=epoch,nonce=nonce,timeout=5,
  clock=function() return t end, guard=function() return paused end,
  issue=function(screen,op,args) table.insert(issued,args);return true end,
  inspect=function(actor,sector)
   if change=='getter_error' then error('missing getter') end
   local number=tonumber(actor:sub(3),16)
   local assigned=number==10 and 'present' or 'nil_observed'
   if change=='control_negative' then assigned='nil_observed' end
   if change=='invalid_getter' then assigned=false end
   if change=='nan' then return {assigned=assigned,x=0/0,y=0,z=0,hull=1,actor_key=actor,sector_key=sector} end
   if change=='slow' then t=10 end
   if change=='reentrant' then app:tick() end
   return {assigned=assigned,x=1,y=2,z=3,hull=1,actor_key=actor,sector_key=sector}
  end}
 app=M.new(o)
 return app,issued,function(v) t=v end,function(v) paused=v end
end
local function row(slot,actor,sector,reservation,id)
 return (id or nonce..'-'..slot)..'|'..epoch..'|'..slot..'|'..actor..'|'..sector..'|'..reservation
end
local app,issued=rig();assert(app:start());assert(issued[1].slot==0)
assert(app:response(row(0,'0xa','0xb','occupied')));assert(issued[2].slot==1)
assert(app:response(row(1,'0xc','0xd','empty')));assert(issued[3].slot==2)
local ok,result=app:response(row(2,'0xe','0xb','empty'))
assert(ok and app:state()=='done' and result.classification=='inconclusive')
assert(result.positive_control_observed and result.save_authorized==false and result.seat_free_proven==false)
assert(#result.rows==3 and result.rows[2].assigned=='nil_observed')
for _,kind in ipairs({'getter_error','invalid_getter','nan','slow','reentrant','control_negative'}) do
 local p=rig(kind);assert(p:start());assert(not p:response(row(0,'0xa','0xb','occupied')));assert(p:state()=='failed',kind)
end
local p=rig();assert(p:start());assert(not p:response(row(0,'0xa','0xb','empty')));assert(p:state()=='failed')
p=rig();assert(p:start());assert(not p:response(row(0,'0xa','0xb','occupied',string.rep('c',32)..'-0')));assert(p:state()=='failed')
p=rig();assert(p:start());assert(p:response(row(0,'0xa','0xb','occupied')))
assert(not p:response(row(0,'0xa','0xb','occupied')));assert(p:state()=='failed')
p=rig();assert(p:start());assert(p:response(row(0,'0xa','0xb','occupied')))
assert(p:response(row(1,'0xc','0xd','empty')))
assert(not p:response(row(2,'0xc','0xb','empty')));assert(p:state()=='failed')
p=rig();assert(p:start());assert(p:response(row(0,'0xa','0xb','occupied')))
assert(p:response(row(1,'0xc','0xd','empty')))
assert(not p:response(row(2,'0xe','0xd','empty')));assert(p:state()=='failed')
local timed,_,advance=rig();assert(timed:start());advance(5);assert(not timed:tick());assert(timed:state()=='failed')
local lost,_,_,pause=rig();assert(lost:start());pause(false);assert(not lost:tick());assert(lost:state()=='failed')
print('player-seat calibration synthetic checks passed')
