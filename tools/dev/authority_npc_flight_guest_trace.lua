-- Isolated guest-only instrumentation for the existing guarded motion writer.
-- Does not install a writer or alter its guard; no gameplay support.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_npc_flight_guest~=true then return end
local underlying=assert(X4LAN_AUTHORITY_REGISTRY_MOTION_NATIVE)
X4LAN_AUTHORITY_REGISTRY_MOTION_NATIVE={new=function(options)
 assert(options.role=='GUEST' and options.enabled==true and options.test_nudge~=true)
 local log,clock=options.log,options.clock
 local actor=(tostring(options.actor):gsub('ULL$',''))
 assert(actor:match('^%d+$') and actor~='0')
 options.log=function(line)
  local kind,rest=line:match('^AUTHORITY_CONTINUOUS_(%u+) (.*)$')
  if kind=='WRITE' or kind=='OBSERVE' then
   local now=clock();assert(type(now)=='number' and now==now and now>=0 and now~=math.huge)
   log(('NATURAL_GUEST_%s epoch=%s index=%.0f frame=%s actor=%s real_time=%.17g %s'):format(kind,options.epoch,options.index,options.frame,actor,now,rest))
  end
  log(line)
 end
 return underlying.new(options)
end}
