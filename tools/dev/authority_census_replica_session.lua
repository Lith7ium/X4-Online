-- Private client session; the existing load owner remains the only update owner.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_census_pair~=true or cfg.authority_census_role~='client' then return end
local owner
function X4LAN_CENSUS_PAIR_TICK()
 local ok=pcall(function()
  if not owner then
   owner=assert(X4LAN_CENSUS_REPLICA_UDP.new_x4({enabled=true,
    base_adapter=X4LAN_CENSUS_JOB_OWNER_X4,base_owner=X4LAN_CENSUS_JOB_OWNER,
    replica_adapter=X4LAN_CENSUS_REPLICA_CLIENT_X4,replica_driver=X4LAN_CENSUS_REPLICA_CLIENT,
    host=X4LAN_AUTHORITY_JOB_REGISTRY_HOST,probe=X4LAN_AUTHORITY_JOB_REGISTRY_PROBE,
    descriptor=X4LAN_AUTHORITY_PAUSED_JOB_DESCRIPTOR,descriptor_core=X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE,
    witness=X4LAN_SECTOR_WITNESS_RUNTIME,role=cfg.authority_census_role,
    epoch=cfg.authority_census_epoch,attempt=cfg.authority_census_attempt,lease=cfg.authority_census_lease,
    nonce=cfg.authority_census_nonce,port=cfg.authority_census_port,timeout=cfg.authority_census_timeout,
    window=cfg.authority_census_window,expected_save_path=cfg.authority_load_save_path,
    guard=function()return true end}))
  end
  assert(owner:tick())
 end)
 if not ok then DebugError('[X4LAN] AUTH_CENSUS_REPLICA ERROR FAULT');error('census replica owner failed') end
end
