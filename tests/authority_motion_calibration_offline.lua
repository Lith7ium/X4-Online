local mode=assert(arg[1])
local actual=assert(loadfile('src/authority/lua/motion_buffer.lua'))()
local M=assert(loadfile('tools/dev/authority_motion_calibration_offline.lua'))()
local t,g=100,100;local pos={0,0,0};local actor='actor';local parent='zone';local safe=true
local issued,reported={},nil;local stop_game=false
local function clock(dt)t=t+dt;if not stop_game then g=g+dt end end
local motion=actual
if mode=='unknown_rate' or mode=='unknown_later' then
 motion={new=function(opt)
  local core=actual.new(opt);local calls=0
  return {push=function(_,...)return core:push(...) end,render=function(_,now)
   local r,e=core:render(now);calls=calls+1
   if r and ((mode=='unknown_rate' and calls==2) or (mode=='unknown_later' and calls==3)) then r.linear_velocity=nil end
   return r,e
  end}
 end}
end
local function observe()
 return {real=t,game=g,pos={pos[1],pos[2],pos[3]},running=safe,actor_valid=safe,player_excluded=safe,undocked=safe,
  pilot_absence_checked=safe,no_orders_checked=safe,frame_alignment_checked=safe,test_volume_checked=safe,
  actor=actor,sector='sector',parent=parent,epoch='epoch',frame='frame'}
end
local owner=assert(M.new({enabled=true,motion=motion,epoch='epoch',frame='frame',observe=observe,
 issue_pose=function(r)
  issued[#issued+1]='pose';pos={r.pos[1],r.pos[2],r.pos[3]}
  if mode=='dispatch_exception' then error('after send') end
  if mode=='guard_loss_after_dispatch' then safe=false end
  if mode=='slow_dispatch' then clock(9) end
  return true
 end,
 issue_velocity=function(r)
  assert(type(r.velocity)=='table' and #r.velocity==3 and r.velocity[1]>0 and r.velocity[2]>0 and r.velocity[3]<0)
  issued[#issued+1]='velocity';return true
 end,
 report=function(r)reported=r;if mode=='report_guard_loss' then safe=false end;return true end}))
assert(M.native_ready()==false)
assert(M.new({})==nil)
assert(owner:start())
if mode=='unsafe_before' then safe=false;clock(1);assert(not owner:tick());assert(#issued==0);return end
if mode=='real_clock_reverse' then t=t-1;assert(not owner:tick());return end
if mode=='game_clock_reverse' then g=g-1;assert(not owner:tick());return end
if mode=='nan_position' then pos[1]=0/0;assert(not owner:tick());return end
if mode=='actor_change' then actor='other';clock(1);assert(not owner:tick());return end
if mode=='parent_change' then parent='other';clock(1);assert(not owner:tick());return end
if mode=='stationary_game_clock' then stop_game=true;for i=1,5 do clock(.025);assert(owner:tick()==(i<4)) end;return end
clock(1);assert(owner:tick());clock(.06)
if mode=='unknown_rate' or mode=='dispatch_exception' or mode=='guard_loss_after_dispatch' or mode=='slow_dispatch' then
 assert(not owner:tick());assert(owner:state()=='failed');assert(owner:mutation_attempted()==(mode~='unknown_rate'));return
end
assert(owner:tick());assert(#issued==1 and issued[1]=='pose')
if mode=='nil_ack' then assert(not owner:ack(nil,'pose-1'));assert(owner:state()=='failed');return end
if mode=='wrong_ack' then assert(not owner:ack('pose','wrong'));assert(owner:state()=='failed');return end
if mode=='timeout' then clock(10);assert(not owner:ack('pose','pose-1'));return end
assert(owner:ack('pose','pose-1'))
if mode=='duplicate_ack' then assert(not owner:ack('pose','pose-1'));return end
clock(.5)
if mode=='unknown_later' then assert(not owner:tick());assert(#issued==1);return end
assert(owner:tick());assert(#issued==2 and issued[2]=='velocity');assert(owner:ack('velocity','velocity-1'))
clock(mode=='delayed_first' and .9 or .5);pos={pos[1]+.5,pos[2]+.25,pos[3]-.125};assert(owner:tick())
if mode=='delayed_first' then assert(owner:tick() and owner:state()=='velocity_observe2' and reported==nil) end
clock(.5);pos={pos[1]+.5,pos[2]+.25,pos[3]-.125}
if mode=='report_guard_loss' then assert(not owner:tick());assert(reported and owner:state()=='failed');return end
assert(owner:tick());assert(owner:state()=='done')
assert(reported and reported.native_start_ready==false and reported.native_velocity_readback==false and reported.restoration_proven==false)
assert(#reported.evidence.samples==2 and #reported.evidence.renders==3)
assert(reported.evidence.renders[1].linear_velocity==nil and reported.evidence.renders[2].linear_velocity[1]>0)
assert(reported.sample2.real>reported.sample1.real and reported.sample2.game>reported.sample1.game)
assert(not owner:ack('velocity','velocity-1'))
