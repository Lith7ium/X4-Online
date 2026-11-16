-- Default-off diagnostic. The isolated load probe owns the only onUpdate.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_sector_create_run~=true then return end
local ffi=require('ffi');local C=ffi.C
local phase='new';local stage='guard';local owner,failed,start,last,game0,quiet=nil,false,nil,nil,nil,nil
local function log(s) DebugError('[X4LAN] AUTH_SECTOR_CREATE '..s) end
local function fail() if not failed then failed=true;phase='failed';log('ERROR RUN_FAIL '..stage) end end
local function diagnostic(message)
 assert(type(message)=='string' and message:match('^[A-Z_a-z ]+$'))
 if message:match('^DISPATCH ') then log('DIAG '..message) else log('ERROR '..message) end
end
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function guard()
 local p=C.GetSaveFolderPath()
 assert(p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 assert(C.IsPlayerValid() and C.IsGamePaused())
 local t=GetCurRealTime();local game=tonumber(C.GetCurrentGameTime())
 assert(finite(t) and t>=0 and (not last or t>=last) and finite(game) and game>=0)
 last=t;start=start or t;assert(t-start<=cfg.authority_sector_create_deadline)
 game0=game0 or game;assert(game==game0)
 return t,game
end
local function report(row)
 assert(phase=='running' and type(row)=='table' and finite(row.x) and finite(row.y) and finite(row.z)
  and finite(row.count) and finite(row.game) and row.game==game0)
 log(('ROW index=%d stage=%s macro=%s location=%s x=%.17g y=%.17g z=%.17g count=%.0f game=%.17g'):
  format(row.index,row.stage,row.sector_macro,row.location,row.x,row.y,row.z,row.count,row.game))
 return true
end
function X4LAN_SECTOR_CREATE_RUN_TICK()
 if failed then error('sector create experiment failed') end
 local ok=pcall(function()
  stage='guard';local t=guard()
  if phase=='new' then
   phase='running';stage='owner_setup'
   owner=assert(X4LAN_SECTOR_CREATE_OWNER.new_x4({enabled=true,exclusive_events=true,
    expected_save_path=cfg.authority_read_save_path,epoch=cfg.authority_sector_epoch,
    nonce=cfg.authority_sector_create_nonce,macros=cfg.authority_sector_create_macros,
    driver_module=assert(X4LAN_SECTOR_CREATE_DRIVER),report=report,diagnostic=diagnostic}))
   stage='owner_start';assert(owner:start())
  elseif phase=='running' then
   stage='owner_update';owner:update();assert(owner:state()~='failed')
   if owner:state()=='pending_fence' then quiet=t;phase='settling';log('PENDING') end
  elseif phase=='settling' then
   stage='settling';owner:update();assert(owner:state()=='pending_fence')
   if t-quiet>=0.5 then log('DONE game='..string.format('%.17g',game0));phase='done' end
  else stage='done_check';assert(phase=='done' and owner:state()=='pending_fence') end
 end)
 if not ok then fail();error('sector create experiment failed') end
 return phase=='done'
end
