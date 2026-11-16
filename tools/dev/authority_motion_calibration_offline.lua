-- Synthetic preparation only: no X4 adapter, hooks, MD commands or I/O.
-- Caller-supplied guard claims are not proof of any native safety condition.
local M={}
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function vec(v,n)
 if type(v)~='table' or #v~=n then return false end
 for i=1,n do if not finite(v[i]) then return false end end
 return true
end
local function distance(a,b)
 return math.sqrt((a[1]-b[1])^2+(a[2]-b[2])^2+(a[3]-b[3])^2)
end
local function copy(v,n)local out={};for i=1,n do out[i]=v[i] end;return out end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(type(o.motion)=='table' and type(o.motion.new)=='function')
 for _,k in ipairs({'observe','issue_pose','issue_velocity','report'})do assert(type(o[k])=='function',k..' required')end
 assert(type(o.epoch)=='string' and #o.epoch>0 and type(o.frame)=='string' and #o.frame>0)
 local phase='new';local failed,busy=false,false;local mutation_attempted=false
 local last,clock_anchor,deadline,ref,baseline,base_at,warm_at,request_at,req,velocity_sample,track,rendered
 local evidence={samples={},renders={},operations={}}
 local rate={1,.5,-.25,0,0,0}
 local function fail(reason)
  failed=true;phase='failed';return false,reason
 end
 local function external(f,...)
  if busy then return fail('reentrant') end
  busy=true;local p=phase;local ok,a,b=pcall(f,...);busy=false
  if not ok or failed or p~=phase then return fail('callback') end
  return true,a,b
 end
 local function guard()
  if failed then return nil end
  local called,s=external(o.observe)
  if not called or type(s)~='table' or not finite(s.real) or not finite(s.game) or s.real<0 or s.game<0 or not vec(s.pos,3) or
   s.running~=true or s.actor_valid~=true or s.player_excluded~=true or s.undocked~=true or
   s.pilot_absence_checked~=true or s.no_orders_checked~=true or s.frame_alignment_checked~=true or
   s.test_volume_checked~=true or s.epoch~=o.epoch or s.frame~=o.frame or
   type(s.actor)~='string' or s.actor=='' or type(s.sector)~='string' or s.sector=='' or type(s.parent)~='string' or s.parent=='' then
   fail('guard');return nil
  end
  if ref and (ref.actor~=s.actor or ref.sector~=s.sector or ref.parent~=s.parent) then fail('identity');return nil end
  ref=ref or {actor=s.actor,sector=s.sector,parent=s.parent}
  if deadline and s.real>=deadline then fail('deadline');return nil end
  if last then
   local dr,dg=s.real-last.real,s.game-last.game
   if dr<0 or dg<0 then fail('clock');return nil end
  end
  if not clock_anchor then clock_anchor={real=s.real,game=s.game} else
   local dr,dg=s.real-clock_anchor.real,s.game-clock_anchor.game
   if dr>=.1 then
    if dg/dr<.95 or dg/dr>1.05 then fail('clock');return nil end
    clock_anchor={real=s.real,game=s.game}
   end
  end
  if baseline and distance(s.pos,baseline)>10 then fail('displacement');return nil end
  last={real=s.real,game=s.game};return s
 end
 local function issue(which,payload,nextphase)
  if not guard() then return false end
  phase=nextphase;request_at=last.real;mutation_attempted=true
  local fn=which=='pose' and o.issue_pose or o.issue_velocity
  local sent_copy={id=payload.id,frame=payload.frame,render_time=payload.render_time}
  if payload.pos then sent_copy.pos=copy(payload.pos,3) end
  if payload.velocity then sent_copy.velocity=copy(payload.velocity,3) end
  local ok,sent=external(fn,sent_copy)
  if not ok or sent~=true then return fail('dispatch_indeterminate') end
  return guard()~=nil
 end
 local api={}
 function api:start()
  if phase~='new' then return fail('start') end
  local s=guard();if not s then return false end
  deadline=s.real+8;baseline=copy(s.pos,3);base_at=s.real
  track=o.motion.new({delay=.15,horizon=2,stale=2,clock_leak=0})
  local ok,why=track:push({sequence=1,frame=o.frame,source_time=s.real,
   pose={baseline[1],baseline[2],baseline[3],0,0,0}},s.real)
  if not ok or why~='append' then return fail('buffer') end
  evidence.samples[1]={sequence=1,source_time=s.real,arrival=s.real,frame=o.frame,pose={baseline[1],baseline[2],baseline[3],0,0,0}}
  phase='baseline';return true
 end
 function api:tick()
  if failed or phase=='done' then return fail('terminal') end
  local s=guard();if not s then return false end
  if phase=='baseline' and s.real-base_at>=1 then
   if s.real-base_at>1.5 or distance(s.pos,baseline)>.5 then return fail('baseline') end
   local dt=s.real-base_at
   local sample={sequence=2,frame=o.frame,source_time=s.real,
    pose={baseline[1]+rate[1]*dt,baseline[2]+rate[2]*dt,baseline[3]+rate[3]*dt,0,0,0},rate=copy(rate,6)}
   local ok,why=track:push(sample,s.real);if not ok or why~='append' then return fail('buffer') end
   evidence.samples[2]={sequence=2,source_time=s.real,arrival=s.real,frame=o.frame,pose=copy(sample.pose,6),rate=copy(sample.rate,6)}
   local first=track:render(s.real);if not first or first.frame~=o.frame or first.linear_velocity~=nil then return fail('warmup') end
   evidence.renders[1]={time=s.real,game=s.game,phase=first.phase,pose=copy(first.pose,6),linear_velocity=nil}
   warm_at=s.real;phase='warm'
  elseif phase=='warm' and s.real-warm_at>=.05 then
   local v=track:render(s.real)
   if not v or v.frame~=o.frame or v.phase~='interpolated' or not vec(v.pose,6) or not vec(v.linear_velocity,3) or distance(v.pose,baseline)>5 then return fail('render') end
   for i=1,3 do if math.abs(v.linear_velocity[i])>5 then return fail('rate') end end
   rendered=v;evidence.renders[2]={time=s.real,game=s.game,phase=v.phase,pose=copy(v.pose,6),linear_velocity=copy(v.linear_velocity,3)}
   req={id='pose-1',frame=o.frame,pos=copy(v.pose,3),render_time=s.real}
   evidence.operations.pose={id=req.id,requested_real=s.real,requested_game=s.game,target=copy(req.pos,3)}
   return issue('pose',req,'pose_wait')
  elseif phase=='pose_settle' and s.real-request_at>=.4 then
   if distance(s.pos,req.pos)>1 then return fail('pose_readback') end
   local v=track:render(s.real)
   if not v or v.frame~=o.frame or (v.phase~='interpolated' and v.phase~='extrapolated') or not vec(v.linear_velocity,3) then return fail('unknown_rate') end
   for i=1,3 do if math.abs(v.linear_velocity[i])>5 then return fail('rate') end end
   evidence.operations.pose.readback={real=s.real,game=s.game,pos=copy(s.pos,3)}
   rendered=v;evidence.renders[3]={time=s.real,game=s.game,phase=v.phase,pose=copy(v.pose,6),linear_velocity=copy(v.linear_velocity,3)}
   req={id='velocity-1',frame=o.frame,velocity=copy(v.linear_velocity,3),render_time=s.real}
   evidence.operations.velocity={id=req.id,requested_real=s.real,requested_game=s.game,vector=copy(req.velocity,3)}
   return issue('velocity',req,'velocity_wait')
  elseif phase=='velocity_observe' and s.real-request_at>=.4 then
   velocity_sample={real=s.real,game=s.game,pos=copy(s.pos,3)};phase='velocity_observe2'
  elseif phase=='velocity_observe2' and s.real-request_at>=.8 and s.real-velocity_sample.real>=.4 then
   if s.game<=velocity_sample.game then return fail('sample_clock') end
   local result={frame=o.frame,pose_request_id='pose-1',velocity_request_id='velocity-1',
    evidence=evidence,velocity=copy(req.velocity,3),sample1=velocity_sample,sample2={real=s.real,game=s.game,pos=copy(s.pos,3)},
    native_velocity_readback=false,native_start_ready=false,restoration_proven=false}
   local ok,accepted=external(o.report,result);if not ok or accepted~=true or not guard() then return fail('report') end
   phase='done';return true
  end
  return true
 end
 function api:ack(kind,id)
  if failed or phase=='done' then return fail('late_ack') end
  if not guard() then return false end
  if (kind~='pose' and kind~='velocity') or type(id)~='string' or not req or kind..'-1'~=req.id or id~=req.id then return fail('unexpected_ack') end
  if phase=='pose_wait' and kind=='pose' then evidence.operations.pose.receipt={real=last.real,game=last.game};request_at=last.real;phase='pose_settle';return true end
  if phase=='velocity_wait' and kind=='velocity' then evidence.operations.velocity.receipt={real=last.real,game=last.game};request_at=last.real;phase='velocity_observe';return true end
  return fail('unexpected_ack')
 end
 function api:state()return phase end
 function api:mutation_attempted()return mutation_attempted end
 return api
end
-- This file deliberately cannot supply native guards or start a native test.
function M.native_ready()return false,'native safety prerequisites unproven' end
return M
