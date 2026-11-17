-- Private registered-fixture seat owner. The load callback owns onUpdate.
local cfg = X4LAN_CONFIG
if not cfg or cfg.authority_registered_player_control ~= true then return end
local ffi = require('ffi')
if not pcall(ffi.typeof, 'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
ffi.cdef[[bool IsGamePaused(void); bool IsPlayerValid(void); bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID); bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool); double GetCurrentGameTime(void);
 UniverseID GetPlayerContainerID(void); UniverseID GetPlayerOccupiedShipID(void);
 UniverseID GetPlayerControlledShipID(void); const char* GetSaveFolderPath(void);]]
local C = ffi.C
local original
local function finite(value) return type(value)=='number' and value==value and math.abs(value)<math.huge end
local function context()
 local container = C.GetPlayerContainerID()
 assert(container~=0 and C.IsValidComponent(container))
 local sector = C.GetContextByClass(container,'sector',true)
 assert(sector~=0 and C.IsValidComponent(sector) and C.IsComponentClass(sector,'sector'))
 return {container=container,sector=sector,ship=C.GetContextByClass(container,'ship',true),
  occupied=C.GetPlayerOccupiedShipID(),controlled=C.GetPlayerControlledShipID()}
end
local function equal(a,b)
 return a.container==b.container and a.sector==b.sector and a.ship==b.ship and
  a.occupied==b.occupied and a.controlled==b.controlled
end
local function one_of(value,a,b) return value==a or value==b or value==0 end
local function guard(mode,target,locked)
 local before=GetCurRealTime();local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_load_save_path)
 assert(C.IsPlayerValid() and C.IsGamePaused())
 local current=context();original=original or current
 if mode=='pre' then
  assert(equal(current,original))
 else
  assert(mode=='post' and target and C.IsValidComponent(target.ship) and C.IsComponentOperational(target.ship) and
   C.IsComponentClass(target.ship,'ship') and C.GetContextByClass(target.ship,'sector',false)==target.sector)
  assert((current.container==original.container or current.container==target.ship) and
   (current.sector==original.sector or current.sector==target.sector) and
   one_of(current.ship,original.ship,target.ship) and one_of(current.occupied,original.occupied,target.ship) and
   one_of(current.controlled,original.controlled,target.ship))
  if locked then
   assert(current.container==target.ship and current.sector==target.sector and current.ship==target.ship and
    current.occupied==target.ship and current.controlled==target.ship)
  end
 end
 local game=tonumber(C.GetCurrentGameTime());local after=GetCurRealTime()
 assert(finite(before) and finite(after) and after>=before and C.IsGamePaused())
 return after,game
end
local function target(value)
 assert(type(value)=='string' and #value<=160)
 local nonce,epoch,ship_text,sector_text=value:match('^([0-9a-f]+)|([0-9a-f]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)$')
 assert(nonce==cfg.authority_fixture_nonce and epoch==cfg.authority_fixture_epoch)
 local ship=X4LAN_RESOLVE_STRING.parse_hex(ship_text);local sector=X4LAN_RESOLVE_STRING.parse_hex(sector_text)
 assert(ship and sector and C.IsValidComponent(ship) and C.IsComponentOperational(ship) and
  C.IsComponentClass(ship,'ship') and C.IsValidComponent(sector) and C.IsComponentClass(sector,'sector') and
  C.GetContextByClass(ship,'sector',false)==sector)
 local already_controlled=ship==original.container and ship==original.ship and
  ship==original.occupied and ship==original.controlled and sector==original.sector
 local separate=ship~=original.container and ship~=original.ship and
  ship~=original.occupied and ship~=original.controlled
 assert(already_controlled or separate)
 return {ship=ship,sector=sector}
end
local controlled=false
local function log(value)
 if value=='CONTROLLED' then controlled=true end
 DebugError('[X4LAN] AUTH_REGISTERED_PLAYER_SEAT '..cfg.authority_fixture_nonce..' '..value)
end
local app=X4LAN_AUTHORITY_PLAYER_CONTROL_LIVE_OWNER.new{enabled=true,timeout=cfg.authority_fixture_timeout,
 guard=guard,target=target,make=function(pre,post)
  return X4LAN_AUTHORITY_PLAYER_CONTROL_ONCE.new_x4{enabled=true,epoch=cfg.authority_fixture_epoch,
   nonce=cfg.authority_fixture_nonce,slot=cfg.authority_fixture_slot,allow_existing=true,
   timeout=math.min(10,cfg.authority_fixture_timeout/2),expected_save_path=cfg.authority_load_save_path,
   pre_guard=pre,post_guard=post,teleport_phase=function(stage)
    assert(stage=='INTENT_TELEPORT' or stage=='LOCAL_CALL_RETURNED')
    log(stage)
   end}
 end,log=log}
RegisterEvent('X4AuthorityPlayerControlOnce.Created',function(_,value)app:created(value)end)
RegisterEvent('X4AuthorityPlayerControlOnce.Dispatched',function(_,value)app:dispatched(value)end)
RegisterEvent('X4AuthorityPlayerControlOnce.ReadResult',function(_,value)app:response(value)end)
RegisterEvent('X4AuthorityPlayerControlOnce.Refused',function()app:refused()end)
local fenced=false
function X4LAN_REGISTERED_PLAYER_CONTROL_TICK()
 if fenced then return true end
 if not app:tick() then error('saved fixture control probe failed') end
 -- DONE is logged inside the owner before its final post-action guard. Emit
 -- FENCED only after tick has returned successfully through that guard.
 if app:state()=='done' and not fenced then
  assert(controlled, 'registered fixture seat unconfirmed')
  fenced=true
  log('FENCED slot='..cfg.authority_fixture_slot..' index='..(cfg.authority_fixture_slot+2))
 end
 return fenced
end
