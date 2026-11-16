-- Installed only in private pair-create profiles; existing load owner drives it.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_pair_create~=true then return end
local session
function X4LAN_PAIR_CREATE_TICK()
 local ok=pcall(function()
  if not session then
   session=assert(X4LAN_PAIR_CREATE_UDP.new_x4({enabled=true,role=cfg.authority_pair_role,
    lease=cfg.authority_pair_lease,attempt=cfg.authority_pair_attempt,epoch=cfg.authority_sector_epoch,
    nonce=cfg.authority_pair_nonce,sector=cfg.authority_pair_macros[1],
    timeout=math.min(cfg.authority_pair_deadline,600),port=cfg.authority_pair_port,
    expected_save_path=cfg.authority_read_save_path,driver=X4LAN_PAIR_CREATE_DRIVER,
    adapter=X4LAN_PAIR_CREATE_X4,pair_guard=X4LAN_SECTOR_PAIR_TICK}))
  end
  assert(session:tick())
 end)
 if not ok then DebugError('[X4LAN] AUTH_PAIR_CREATE ERROR FAULT');error('pair create session failed') end
end
