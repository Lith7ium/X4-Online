-- Read-only saved-fixture registry verification, driven by the recovery owner.
local cfg = X4LAN_CONFIG
if not cfg or cfg.authority_saved_registry_verify ~= true then return end
local ffi = require('ffi')
ffi.cdef[[bool IsGamePaused(void); bool IsPlayerValid(void); const char* GetSaveFolderPath(void);]]
local C = ffi.C
local phase, started, last_time, failed = 'new', nil, nil, false
local function guard()
 local now = GetCurRealTime()
 assert(type(now)=='number' and now==now and now>=0 and now<math.huge)
 assert(not last_time or now>=last_time)
 started=started or now;last_time=now
 assert(now-started<cfg.authority_saved_registry_timeout)
 local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and
  ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_load_save_path)
 assert(C.IsPlayerValid() and C.IsGamePaused())
end
local function fail()
 if not failed then failed=true;DebugError('[X4LAN] AUTH_SAVED_REGISTRY_VERIFY ERROR') end
end
RegisterEvent('X4AuthoritySavedRegistryVerify.Refused', function() fail() end)
RegisterEvent('X4AuthoritySavedRegistryVerify.Matched', function(_, value)
 local ok=pcall(function()
  assert(not failed and phase=='waiting');guard()
  assert(value==cfg.authority_saved_registry_nonce..'|'..cfg.authority_fixture_epoch..'|4|3|4')
  guard();phase='received'
 end)
 if not ok then fail() end
end)
function X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()
 if failed then error('saved fixture registry verification failed') end
 if phase=='done' then return end
 local completed=false
 local ok=pcall(function()
  guard()
  if phase=='new' then
   assert(type(cfg.authority_saved_registry_nonce)=='string' and
    cfg.authority_saved_registry_nonce:match('^[0-9a-f]+$') and #cfg.authority_saved_registry_nonce==32)
   assert(type(cfg.authority_fixture_epoch)=='string' and
    cfg.authority_fixture_epoch:match('^[0-9a-f]+$') and #cfg.authority_fixture_epoch==32)
   phase='waiting'
   assert(AddUITriggeredEvent('X4AuthoritySavedRegistryVerify','Read',
    {epoch=cfg.authority_fixture_epoch,request_id=cfg.authority_saved_registry_nonce})~=false)
  elseif phase=='received' then
   phase='finalizing';completed=true
  else assert(phase=='waiting') end
  guard()
 end)
 if not ok then fail();error('saved fixture registry verification failed') end
 if completed then phase='done';DebugError('[X4LAN] AUTH_SAVED_REGISTRY_VERIFY MATCHED 4 3 4') end
end
