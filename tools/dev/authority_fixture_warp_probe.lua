-- Explicit one-process disposable diagnostic: one saved MD fixture reference.
-- No native pose/velocity setter, and no collision or atomicity claim.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_fixture_warp~=true then return end
local ffi=require('ffi');local C=ffi.C
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
ffi.cdef[[bool IsStartmenu(void);bool IsPlayerValid(void);bool IsSaveListLoadingComplete(void);
void ReloadSaveList(void);const char* GetSaveFolderPath(void);bool IsValidComponent(UniverseID);
bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
UniverseID GetContextByClass(UniverseID,const char*,bool);UIPosRot GetObjectPositionInSector(UniverseID);
UniverseID GetPlayerControlledShipID(void);UniverseID GetPlayerOccupiedShipID(void);UniverseID GetPlayerContainerID(void);]]
local stage='initial';local actor,sector,zone,before,target,ack_at;local failed=false
local function log(s) DebugError('[X4LAN] AUTH_WARP '..s) end
local function fail() if not failed then failed=true;log('ERROR') end end
local function key(v) return v and v~=0 and (tostring(v):gsub('ULL$','')) or '' end
local function lua_id(v) return ConvertStringToLuaID(key(v)) end
local function check_profile()
 local p=C.GetSaveFolderPath();assert(p~=nil and p~=ffi.NULL)
 assert(cfg.test_profile=='45841' and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_fixture_save_path)
end
local function guard()
 assert(actor and C.IsValidComponent(actor) and C.IsComponentOperational(actor) and C.IsComponentClass(actor,'ship'))
 local s=C.GetContextByClass(actor,'sector',false);local z=C.GetContextByClass(actor,'zone',false)
 assert(key(s)~='' and key(z)~='')
 if sector then assert(key(s)==key(sector) and key(z)==key(zone)) else sector,zone=s,z end
 local controlled,occupied,container=C.GetPlayerControlledShipID(),C.GetPlayerOccupiedShipID(),C.GetPlayerContainerID()
 for _,v in ipairs({controlled,occupied,container}) do assert(key(v)~=key(actor)) end
 assert(key(container)~='' and C.IsValidComponent(container),'local player container unknown')
 local ship=C.GetContextByClass(container,'ship',true)
 if key(ship)~='' then assert(key(ship)~=key(actor))
 else assert(key(C.GetContextByClass(container,'station',true))~='', 'player ship/station context unknown') end
 local docked,docking,stored=GetComponentData(lua_id(actor),'isdocked','isdocking','isinternallystored')
 assert(docked==false and docking==false and stored==false)
end
local function pose()
 local p=C.GetObjectPositionInSector(actor);local out={x=tonumber(p.x),y=tonumber(p.y),z=tonumber(p.z)}
 for _,v in pairs(out) do assert(v and v==v and v~=math.huge and v~=-math.huge) end
 return out
end
local function log_pose(label,p)
 log(('%s x=%.17g y=%.17g z=%.17g'):format(label,p.x,p.y,p.z))
end
RegisterEvent('X4LAN_NativeGate.Actor1',function(_,v)
 if stage=='restoring' then assert(not actor);actor=ffi.new('UniverseID',ConvertIDTo64Bit(v)) end
end)
RegisterEvent('X4LAN_NativeGate.Restored',function()
 if stage=='restoring' then stage='restored' end
end)
RegisterEvent('X4LAN_NativeGate.Missing',function() fail() end)
RegisterEvent('X4LAN_FixtureWarp.Result',function(_,v)
 if stage~='await_ack' or v~='applied' then fail();return end
 stage='ack';ack_at=GetCurRealTime();log('ACK')
end)
local function frame()
 if failed or stage=='done' then return end
 if stage=='initial' then
  if C.IsStartmenu() then check_profile();C.ReloadSaveList();stage='list';log('LOAD_ARMED');return end
  if not C.IsPlayerValid() then return end
  check_profile();stage='restoring';log('LOADED');AddUITriggeredEvent('X4LAN_NativeGate','RestoreActors',{});return
 end
 if stage=='list' then
  assert(C.IsStartmenu());if not C.IsSaveListLoadingComplete() then return end
  local entries=GetSaveList({save_009=true});assert(type(entries)=='table');local count=0
  for _,e in pairs(entries) do if e.filename=='save_009' then count=count+1 end end
  assert(count==1);stage='loading';log('LOAD_REQUEST');LoadGame('save_009');return
 end
 if stage=='restored' then
  guard();before=pose();target={x=before.x+10,y=before.y,z=before.z}
  log_pose('BEFORE',before);stage='await_ack';log('REQUEST')
  AddUITriggeredEvent('X4LAN_FixtureWarp','Once',{ship=lua_id(actor),sector=lua_id(sector),parent=lua_id(zone),x=target.x,y=target.y,z=target.z})
  return
 end
 if stage=='ack' then
  guard();local p=pose();log_pose('IMMEDIATE',p);stage='settling';return
 end
 if stage=='settling' and GetCurRealTime()-ack_at>=1 then
  guard();local p=pose();local elapsed=GetCurRealTime()-ack_at
  log(('LATE x=%.17g y=%.17g z=%.17g elapsed=%.17g'):format(p.x,p.y,p.z,elapsed));stage='done'
 end
end
SetScript('onUpdate',function() local ok=pcall(frame);if not ok then fail() end end)
