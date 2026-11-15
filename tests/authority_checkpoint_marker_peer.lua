local phase=arg[1]
local scenario=arg[2] or 'success'
local nonce='aabbccddeeff00112233445566778899'
X4LAN_CONFIG={authority_marker_phase=phase}
if phase=='save' then X4LAN_CONFIG.authority_marker=nonce end
local events={};local request;local requests=0;local now=1
function GetCurRealTime() return now end
function RegisterEvent(name,callback) events[name]=callback end
function DebugError() end
function AddUITriggeredEvent(screen,control,params)
 assert(screen=='X4AuthorityCheckpointMarker');request={control,params};requests=requests+1
end
dofile('tools/dev/authority_checkpoint_marker_probe.lua')
assert(not X4LAN_AUTHORITY_MARKER_READY())
assert(not X4LAN_AUTHORITY_MARKER_READY())
if phase=='save' then
 assert(request[1]=='Store' and request[2].marker==nonce)
 events['X4AuthorityCheckpointMarker.Stored'](nil,nonce)
else
 assert(request[1]=='Inspect' and next(request[2])==nil)
 if scenario=='retry' then
  events['X4AuthorityCheckpointMarker.Missing']()
  now=now+.49;assert(not X4LAN_AUTHORITY_MARKER_READY());assert(requests==1)
  now=now+.02;assert(not X4LAN_AUTHORITY_MARKER_READY());assert(requests==2)
 elseif scenario=='timeout' then
  events['X4AuthorityCheckpointMarker.Missing']()
  now=61;assert(not pcall(X4LAN_AUTHORITY_MARKER_READY))
  return
 elseif scenario=='unanswered' then
  now=61;assert(not pcall(X4LAN_AUTHORITY_MARKER_READY))
  return
 end
 events['X4AuthorityCheckpointMarker.Inspected'](nil,nonce)
end
assert(X4LAN_AUTHORITY_MARKER_READY())
events['X4AuthorityCheckpointMarker.Missing']()
assert(not pcall(X4LAN_AUTHORITY_MARKER_READY))
