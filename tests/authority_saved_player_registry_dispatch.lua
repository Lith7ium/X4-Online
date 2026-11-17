local callbacks, logs, seat_ticks = {}, {}, 0
X4LAN_CONFIG = {authority_saved_player_registry=true, authority_fixture_epoch=string.rep('a',32),
 authority_registry_enroll_nonce=string.rep('b',32), authority_fixture_timeout=60,
 authority_load_save_path='/tmp/45841/save'}
X4LAN_SHIP_REGISTRY_CLIENT, X4LAN_RESOLVE_STRING = {}, {}
RegisterEvent = function(name, callback) callbacks[name]=callback end
DebugError = function(value) logs[#logs+1]=value end
X4LAN_AUTHORITY_RECOVERY_SEAT_TICK = function() seat_ticks=seat_ticks+1 end
local registry_events, fixture_events, phase = {}, {}, 'new'
X4LAN_PLAYER_REGISTRY_ENROLL = {new_x4=function()
 return {
  start=function() phase='pending';return true end,
  tick=function() phase='done';return true end,
  state=function() return phase end,
  take_result=function() phase='completed';return {indices={3,4},count=4} end,
  fixture_event=function(_,value) fixture_events[#fixture_events+1]=value;return true end,
  registry_event=function(_,name,value)
   registry_events[#registry_events+1]={name,value}
   return phase ~= 'completed'
  end,
 }
end}
dofile('tools/dev/authority_saved_player_registry_dispatch.lua')
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
assert(seat_ticks==0)
callbacks['X4AuthorityPlayerRegistryRead.Result'](nil,'fixture')
callbacks['X4AuthorityShipRegistry.Enrolled'](nil,3)
assert(fixture_events[1]=='fixture' and registry_events[1][1]=='Enrolled' and registry_events[1][2]==3)
X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
assert(seat_ticks==1 and logs[1]=='[X4LAN] AUTH_PLAYER_REGISTRY ENROLLED 3 4')
callbacks['X4AuthorityShipRegistry.Enrolled'](nil,3)
assert(not pcall(X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK) and seat_ticks==1)
