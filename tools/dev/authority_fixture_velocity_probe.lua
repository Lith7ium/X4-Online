-- Explicit one-process disposable diagnostic: one saved MD fixture reference.
-- MD velocity and native position readback only; no collision or atomicity claim.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_fixture_velocity~=true then return end
local ffi=require('ffi');local C=ffi.C
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
ffi.cdef[[bool IsStartmenu(void);bool IsPlayerValid(void);bool IsSaveListLoadingComplete(void);
void ReloadSaveList(void);const char* GetSaveFolderPath(void);bool IsValidComponent(UniverseID);
bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
UniverseID GetContextByClass(UniverseID,const char*,bool);UIPosRot GetObjectPositionInSector(UniverseID);
UniverseID GetPlayerControlledShipID(void);UniverseID GetPlayerOccupiedShipID(void);UniverseID GetPlayerContainerID(void);]]
local stage='initial';local actor,sector,zone,before,baseline_at,start_at,stop_at;local failed=false
local function log(s) DebugError('[X4LAN] AUTH_VELOCITY '..s) end
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
RegisterEvent('X4LAN_FixtureVelocity.Start',function(_,v)
 if stage~='await_start' or v~='applied' then fail();return end
 stage='started';start_at=GetCurRealTime();log('ACK_START')
end)
RegisterEvent('X4LAN_FixtureVelocity.Stop',function(_,v)
 if stage~='await_stop' or v~='applied' then fail();return end
 stage='stopped';stop_at=GetCurRealTime();log('ACK_STOP')
end)
local function timed_pose(label,at)
 guard();local p=pose();local elapsed=GetCurRealTime()-at
 log(('%s x=%.17g y=%.17g z=%.17g elapsed=%.17g'):format(label,p.x,p.y,p.z,elapsed))
 return p
end
local function request(name)
 AddUITriggeredEvent('X4LAN_FixtureVelocity',name,{ship=lua_id(actor),sector=lua_id(sector),parent=lua_id(zone)})
end
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
  guard();before=pose();log_pose('BEFORE',before);baseline_at=GetCurRealTime();stage='baseline';return
 end
 if stage=='baseline' and GetCurRealTime()-baseline_at>=1 then
  local p=timed_pose('BASE',baseline_at)
  -- Refuse to set velocity if the original fixture is already moving.
  local d=math.sqrt((p.x-before.x)^2+(p.y-before.y)^2+(p.z-before.z)^2)
  assert(d<=0.5);stage='await_start';log('REQUEST_START');request('Start');return
 end
 if stage=='started' and GetCurRealTime()-start_at>=1 then
  timed_pose('MOVING1',start_at);stage='moving';return
 end
 if stage=='moving' and GetCurRealTime()-start_at>=2 then
  timed_pose('MOVING2',start_at);stage='await_stop';log('REQUEST_STOP');request('Stop');return
 end
 if stage=='stopped' and GetCurRealTime()-stop_at>=1 then
  timed_pose('STOP1',stop_at);stage='settling';return
 end
 if stage=='settling' and GetCurRealTime()-stop_at>=2 then
  timed_pose('STOP2',stop_at);stage='done';return
 end
end
SetScript('onUpdate',function() local ok=pcall(frame);if not ok then fail() end end)
