-- One recovery update owner runs registry enrollment before the saved seat probe.
local cfg = X4LAN_CONFIG
if not cfg or cfg.authority_saved_player_registry ~= true then return end

local owner, registration_complete, failed = nil, false, false
local function fail()
 if not failed then
  failed = true
  DebugError('[X4LAN] AUTH_PLAYER_REGISTRY ERROR')
 end
end

RegisterEvent('X4AuthorityPlayerRegistryRead.Result', function(_, value)
 if not owner or not owner:fixture_event(value) then fail() end
end)
RegisterEvent('X4AuthorityPlayerRegistryRead.Refused', function() fail() end)
for _, name in ipairs({'Epoch', 'Count', 'Enrolled', 'Actor', 'Refused', 'Unavailable', 'Faulted', 'Uninitialized'}) do
 RegisterEvent('X4AuthorityShipRegistry.' .. name, function(_, value)
  if not owner or not owner:registry_event(name, value) then fail() end
 end)
end

function X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
 if failed then error('fixture registry enrollment failed') end
 if not registration_complete then
  if not owner then
   owner = assert(X4LAN_PLAYER_REGISTRY_ENROLL.new_x4({
    enabled=true, epoch=cfg.authority_fixture_epoch, nonce=cfg.authority_registry_enroll_nonce,
    timeout=cfg.authority_fixture_timeout, expected_save_path=cfg.authority_load_save_path,
    external_guard=function() return true end, registry=X4LAN_SHIP_REGISTRY_CLIENT,
    resolve=X4LAN_RESOLVE_STRING,
   }))
   if not owner:start() then fail(); error('fixture registry start failed') end
  else
   if not owner:tick() then fail(); error('fixture registry tick failed') end
   if owner:state() == 'done' then
    local result = owner:take_result()
    if not result or result.count ~= 4 or result.indices[1] ~= 3 or result.indices[2] ~= 4 then
     fail(); error('fixture registry result failed')
    end
    registration_complete = true
    DebugError('[X4LAN] AUTH_PLAYER_REGISTRY ENROLLED 3 4')
   end
  end
 end
 if registration_complete then X4LAN_AUTHORITY_RECOVERY_SEAT_TICK() end
end
