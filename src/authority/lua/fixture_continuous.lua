-- Disposable, opt-in local experiment. The transmitted rate is a source-time
-- finite difference, not native velocity; only fresh packets are written.
local M={}
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function distance(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2) end
function M.new(env)
 assert(type(env)=='table' and type(env.read)=='function' and type(env.write)=='function' and type(env.clock)=='function' and type(env.log)=='function')
 local last
 return {sample=function(_,packet)
  local now=env.clock();assert(finite(now))
  local before=env.read()
  if last then
   env.log(('AUTHORITY_CONTINUOUS_OBSERVE seq=%.0f x=%.17g y=%.17g z=%.17g'):format(last,before.x,before.y,before.z))
   last=nil
  end
  if not packet then return end
  local current={x=packet.x,y=packet.y,z=packet.z,t=now,seq=packet.source_sequence}
  assert(finite(current.x) and finite(current.y) and finite(current.z) and finite(current.seq))
  local vx,vy,vz=packet.vx,packet.vy,packet.vz
  if not finite(vx) or not finite(vy) or not finite(vz) then return end
  local speed=math.sqrt(vx*vx+vy*vy+vz*vz)
  -- A stationary update is still authoritative: dropping it can leave the
  -- replica at an earlier predicted position after the source has stopped.
  if not finite(speed) or speed>5000 then return end
  -- 100 ms prediction, capped by speed check and only for this fresh packet.
  local target={x=current.x+vx*.1,y=current.y+vy*.1,z=current.z+vz*.1}
  if distance(before,target)>10000 then return end
  env.log(('AUTHORITY_CONTINUOUS_WRITE seq=%.0f x=%.17g y=%.17g z=%.17g vx=%.17g vy=%.17g vz=%.17g target_x=%.17g target_y=%.17g target_z=%.17g before_x=%.17g before_y=%.17g before_z=%.17g'):format(current.seq,current.x,current.y,current.z,vx,vy,vz,target.x,target.y,target.z,before.x,before.y,before.z))
  env.write(target,before)
  last=current.seq
 end}
end
X4LAN_AUTHORITY_FIXTURE_CONTINUOUS=M
return M
