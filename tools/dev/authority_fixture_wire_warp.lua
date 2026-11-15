-- Opt-in test state machine. Environment supplies X4 guard, monotonic clock,
-- logging and a one-shot MD request. No game hooks are installed here.
local M={}
local function distance(a,b)
 local x,y,z=a.x-b.x,a.y-b.y,a.z-b.z
 return math.sqrt(x*x+y*y+z*z)
end
local function row(p)
 return ('x=%.17g y=%.17g z=%.17g'):format(p.x,p.y,p.z)
end
function M.new(env)
 assert(type(env)=='table' and type(env.read)=='function' and type(env.send)=='function'
  and type(env.clock)=='function' and type(env.log)=='function')
 local state={stage='waiting'}
 function state:sample(received)
  local before=env.read()
  if self.stage=='waiting' and received and distance(before,received)>=10 then
   self.target={x=received.x,y=received.y,z=received.z}
   self.stage='requested'
   env.log(('AUTHORITY_APPLY_REQUEST request=%.0f seq=%.0f %s before_%s'):format(
    received.request,received.source_sequence,row(self.target),row(before):gsub(' ', ' before_')))
   env.send(self.target)
  elseif self.stage=='ack' and env.clock()-self.ack_at>=1 then
   local elapsed=env.clock()-self.ack_at
   env.log(('AUTHORITY_APPLY_LATE elapsed=%.9f %s'):format(elapsed,row(before)))
   self.stage='done'
  end
 end
 function state:ack(value)
  assert(self.stage=='requested' and value=='applied','unexpected or refused MD warp')
  self.ack_at=env.clock();self.stage='ack';env.log('AUTHORITY_APPLY_ACK')
 end
 return state
end
X4LAN_AUTHORITY_FIXTURE_WIRE_WARP=M
return M
