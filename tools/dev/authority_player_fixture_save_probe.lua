-- Disposable fixture creation under the existing load/update owner.
-- This observes creation only; it neither proves seat availability nor saves.
local cfg = X4LAN_CONFIG
if not cfg or cfg.authority_player_fixture_save ~= true then return end

local ffi = require('ffi')
ffi.cdef[[bool IsGamePaused(void); bool IsPlayerValid(void);
 double GetCurrentGameTime(void); const char* GetSaveFolderPath(void);]]
local C = ffi.C
local phase, failed, start, previous, game = 'new', false, nil, nil, nil
local function log(value) DebugError('[X4LAN] AUTH_PLAYER_FIXTURE_SAVE '..value) end
local function guard()
 assert(not failed and C.IsPlayerValid() and C.IsGamePaused())
 local path = C.GetSaveFolderPath()
 assert(path ~= nil and path ~= ffi.NULL and
  ffi.string(path):gsub('\\', '/'):gsub('/+$', '') == cfg.authority_read_save_path)
 local now, current = GetCurRealTime(), tonumber(C.GetCurrentGameTime())
 assert(type(now)=='number' and now==now and math.abs(now)<math.huge and now>=0 and
  type(current)=='number' and current==current and math.abs(current)<math.huge and current>=0)
 start = start or now
 assert((not previous or now>=previous) and now-start<cfg.authority_player_fixture_timeout)
 previous = now
 if game then assert(current==game) else game=current end
end
local function action(callback)
 if failed then return false end
 local ok = pcall(function() guard();callback();guard() end)
 if not ok then failed=true;phase='failed';log('ERROR');return false end
 return true
end
RegisterEvent('X4AuthorityPlayerSeatExperiment.Preflight',function(_,value)
 action(function()
  assert(phase=='preflight' and value==cfg.authority_player_fixture_nonce..'|'..cfg.authority_sector_epoch..'|ok')
  phase='create';log('PREFLIGHT')
 end)
end)
RegisterEvent('X4AuthorityPlayerSeatExperiment.Refused',function() failed=true;phase='failed';log('ERROR') end)
RegisterEvent('X4AuthorityPlayerSectorFixture.Created',function(_,value)
 action(function() assert(phase=='creating' and value==2);phase='done';log('CREATED') end)
end)
RegisterEvent('X4AuthorityPlayerSectorFixture.Refused',function() failed=true;phase='failed';log('ERROR') end)
function X4LAN_PLAYER_FIXTURE_SAVE_TICK()
 assert(action(function()
  if phase=='new' then
   phase='preflight'
   assert(AddUITriggeredEvent('X4AuthorityPlayerSeatExperiment','Preflight',
    {epoch=cfg.authority_sector_epoch,request_id=cfg.authority_player_fixture_nonce})~=false)
  elseif phase=='create' then
   phase='creating'
   assert(AddUITriggeredEvent('X4AuthorityPlayerSectorFixture','Create',
    {epoch=cfg.authority_sector_epoch})~=false)
  else assert(phase=='preflight' or phase=='creating' or phase=='done') end
 end))
end
function X4LAN_PLAYER_FIXTURE_SAVE_READY() return not failed and phase=='done' end
