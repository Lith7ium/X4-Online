-- Isolated test only. The client is deliberately never given the marker in config.
local cfg=X4LAN_CONFIG
if not cfg or not cfg.authority_marker_phase then return end
local phase=cfg.authority_marker_phase
assert(phase=='save' or phase=='load')
local state='new';local failed=false
local deadline,next_inspect,inspections=nil,nil,0
local timeout,interval,max_inspections=60,0.5,120
local function fail() failed=true;DebugError('[X4LAN] AUTH_MARKER '..phase..' ERROR') end
RegisterEvent('X4AuthorityCheckpointMarker.Stored',function(_,marker)
 if phase~='save' or state~='store' or marker~=cfg.authority_marker then fail();return end
 state='done';DebugError('[X4LAN] AUTH_MARKER save STORED '..marker)
end)
RegisterEvent('X4AuthorityCheckpointMarker.Inspected',function(_,marker)
 if phase~='load' or state~='inspect' or type(marker)~='string' or not marker:match('^[0-9a-f]+$') or #marker~=32 then fail();return end
 state='done';DebugError('[X4LAN] AUTH_MARKER load INSPECTED '..marker)
end)
RegisterEvent('X4AuthorityCheckpointMarker.Missing',function()
 -- X4 may expose a player while it is still performing the second load pass.
 -- A missing saved marker/load-event flag is therefore not yet success or a
 -- definitive failure. Wait and ask again, but never accept it as a receipt.
 if phase~='load' or state~='inspect' then fail();return end
 state='waiting';next_inspect=GetCurRealTime()+interval
end)
function X4LAN_AUTHORITY_MARKER_READY()
 if failed then error('checkpoint marker experiment failed') end
 local now=GetCurRealTime()
 if phase=='load' and deadline and now>=deadline and state~='done' then
  fail();error('checkpoint marker load observation timed out')
 end
 if state=='new' then
  if phase=='save' then
   assert(type(cfg.authority_marker)=='string' and #cfg.authority_marker==32 and cfg.authority_marker:match('^[0-9a-f]+$'))
   state='store';AddUITriggeredEvent('X4AuthorityCheckpointMarker','Store',{marker=cfg.authority_marker})
  else
   assert(cfg.authority_marker==nil)
   deadline=now+timeout;state='waiting';next_inspect=now
  end
 end
 if phase=='load' and state=='waiting' and now>=next_inspect then
  if inspections>=max_inspections then fail();error('checkpoint marker inspection limit') end
  inspections=inspections+1;state='inspect'
  AddUITriggeredEvent('X4AuthorityCheckpointMarker','Inspect',{})
 end
 return state=='done'
end
