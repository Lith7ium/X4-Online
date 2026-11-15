-- Opt-in, disposable, one-ship registry/motion diagnostic; no game calls here.
-- The harness must serialize registry Resolve requests: Actor does not include
-- the requested index. Objects and frames are process-local, never wire IDs.
local M={}
local MAX_SEQUENCE=9007199254740991
local function finite(n) return type(n)=='number' and n==n and n~=math.huge and n~=-math.huge end
local function token(v) return type(v)=='string' and #v>0 and #v<=64 and v:match('^[%w_.%-]+$')~=nil end
local function coordinates(p)
 return type(p)=='table' and finite(p.x) and finite(p.y) and finite(p.z)
end

-- resolve(epoch,index) issues the only outstanding MD Resolve request;
-- the harness calls bind(epoch,index,actor) only for that response. An
-- Unavailable, Faulted, unexpected response or game reload must stop the
-- diagnostic; there is no automatic rebind. validate(actor,epoch,index,frame)
-- must check the latest confirmed registry binding, current actor lifetime,
-- direct-parent/sector frame, player exclusion and test-profile guarantees.
-- On client writes, write(actor,frame,target,before) must additionally enforce
-- all guards appropriate to the specific test, including collision clearance.
-- Neither validate nor write is supplied by this module. The fixture wire
-- relay is loopback-only and its fixture label contains the registry identity
-- and frame; its configured frame must be identical at both ends and is never inferred
-- from a process-local sector handle. A persisted checkpoint marker and actual
-- common sector identity must be independently established by the harness.
function M.new(o)
 assert(type(o)=='table' and o.enabled==true and (o.role=='SOURCE' or o.role=='GUEST'))
 assert(type(o.epoch)=='string' and #o.epoch==32 and o.epoch:match('^[0-9a-f]+$'))
 assert(type(o.index)=='number' and o.index>=1 and o.index<=MAX_SEQUENCE and o.index%1==0)
 assert(token(o.frame) and type(o.resolve)=='function' and type(o.validate)=='function')
 assert(type(o.read)=='function' and type(o.clock)=='function' and type(o.log)=='function')
 assert(type(o.wire_module)=='table' and type(o.wire_module.new)=='function')
 assert(type(o.continuous_module)=='table' and type(o.continuous_module.new)=='function')
 assert(o.role~='GUEST' or type(o.write)=='function')
 local fixture=o.epoch..'.'..string.format('%.0f',o.index)..'.'..o.frame
 assert(#fixture<=64,'registry and frame label too long for fixture wire')
 local wire=o.wire_module.new(o.transport,o.role,o.lease,fixture,true)
 local actor,previous,continuous,stopped=nil,nil,nil,false
 local function checked()
  assert(actor~=nil and o.validate(actor,o.epoch,o.index,o.frame)==true,'binding or safety check failed')
  local p=o.read(actor,o.frame)
  assert(coordinates(p),'invalid local position')
  return p
 end
 local function diagnostic_log(line) o.log(line) end
 local api={}
 local function bind(epoch,index,value)
  assert(not stopped and actor==nil and epoch==o.epoch and index==o.index and value~=nil, 'unexpected resolve')
  actor=value
  checked()
  if o.role=='GUEST' then
   continuous=o.continuous_module.new({clock=o.clock,log=diagnostic_log,read=checked,
    write=function(target,before)
     checked()
     assert(coordinates(target) and coordinates(before))
     o.write(actor,o.frame,target,before)
    end})
  end
 end
 function api:stop() stopped=true;actor=nil;previous=nil end
 local function step()
  assert(not stopped and actor~=nil,'registry actor unavailable')
  local observed=checked()
  -- Never retain or mutate the engine's returned table; an unavailable rate
  -- must not accidentally reuse a previous observation's velocity.
  local p={x=observed.x,y=observed.y,z=observed.z}
  if o.role=='SOURCE' then
   local now=o.clock();assert(finite(now) and now>=0,'invalid monotonic time')
   if previous then
    local dt=now-previous.t
    assert(dt>=0,'monotonic clock regressed')
    if dt>=.02 and dt<=1 then
     local vx,vy,vz=(p.x-previous.x)/dt,(p.y-previous.y)/dt,(p.z-previous.z)/dt
     if finite(vx) and finite(vy) and finite(vz) and math.sqrt(vx*vx+vy*vy+vz*vz)<=5000 then
      p.vx,p.vy,p.vz=vx,vy,vz
     end
    end
    if dt>=.02 then previous={x=p.x,y=p.y,z=p.z,t=now} end
   else previous={x=p.x,y=p.y,z=p.z,t=now} end
   local before=wire.sent
   wire:step(p)
   if wire.sent>before then
    local rate=p.vx and ('known vx=%.17g vy=%.17g vz=%.17g'):format(p.vx,p.vy,p.vz) or 'unknown'
    o.log(('REGISTRY_MOTION_SOURCE epoch=%s index=%.0f frame=%s seq=%.0f x=%.17g y=%.17g z=%.17g rate=%s'):format(o.epoch,o.index,o.frame,wire.sent,p.x,p.y,p.z,rate))
   end
  else
   local packet=wire:step()
   -- No frame-less or velocity-less write; a zero velocity is still known.
   if packet and packet.fixture==fixture and finite(packet.vx) and finite(packet.vy) and finite(packet.vz) then
    checked()
    continuous:sample(packet)
   else continuous:sample(nil) end
  end
 end
 -- Any failed check permanently stops this instance; a new resolve and fresh
 -- transport are required. In particular, a previously bound object is not
 -- silently reused after a transient lifetime or frame validation failure.
 function api:bind(epoch,index,value)
  local ok,err=pcall(bind,epoch,index,value)
  if not ok then self:stop();error(err) end
 end
 function api:step()
  local ok,err=pcall(step)
  if not ok then self:stop();error(err) end
 end
 o.resolve(o.epoch,o.index)
 return api
end
X4LAN_AUTHORITY_REGISTRY_MOTION=M
return M
