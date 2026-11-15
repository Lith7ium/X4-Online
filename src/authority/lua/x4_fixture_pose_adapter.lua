-- Default-off, single-fixture X4 pose primitive for a disposable test only.
-- Loading this file makes no game call and registers no event. There is no
-- scheduler, transport, Velocity setter, activation/deletion, or game start.
-- The caller must provide trusted private-profile, direct-parent and no-other-
-- player attestations and an independent collision-clearance verifier.
-- None is provided here.
local M={}

local function saved_id(v)
 return type(v)=='string' and #v==16 and v:match('^[0-9a-f]+$') and v~='0000000000000000'
end

local function copy_pose(p)
 assert(type(p)=='table','pose unavailable')
 local out={}
 for _,field in ipairs({'x','y','z','yaw','pitch','roll'}) do
  local v=p[field]
  assert(type(v)=='number' and v==v and v~=math.huge and v~=-math.huge, 'invalid pose')
  out[field]=v
 end
 return out
end

-- Resolve on construction only, after the explicit diagnostic opt-in. The
-- exported API has the same signatures used by the existing X4 UI diagnostics.
local function native_api()
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
 ffi.cdef[[
  const char* GetSaveFolderPath(void);
  bool IsValidComponent(UniverseID);
  bool IsComponentOperational(UniverseID);
  bool IsComponentClass(UniverseID,const char*);
  UniverseID GetContextByClass(UniverseID,const char*,bool);
  UniverseID GetPlayerControlledShipID(void);
  UniverseID GetPlayerOccupiedShipID(void);
  UniverseID GetPlayerContainerID(void);
  UIPosRot GetObjectPositionInSector(UniverseID);
  void SetObjectSectorPos(UniverseID,UniverseID,UIPosRot);
 ]]
 local C=ffi.C
 -- Eagerly resolve required symbols before returning an executable adapter.
 local path,valid,operational,isclass,context=C.GetSaveFolderPath,C.IsValidComponent,
  C.IsComponentOperational,C.IsComponentClass,C.GetContextByClass
 local controlled,occupied,container=C.GetPlayerControlledShipID,C.GetPlayerOccupiedShipID,C.GetPlayerContainerID
 local position,set_position=C.GetObjectPositionInSector,C.SetObjectSectorPos
 return {
  normalize=function(v) return ffi.new('UniverseID',v) end,
  key=function(v) if v==nil or v==0 then return '' end; return (tostring(v):gsub('ULL$','')) end,
  path=function() return (ffi.string(path()):gsub('\\','/'):gsub('/+$','')) end,
  valid=function(v) return valid(v) end,
  operational=function(v) return operational(v) end,
  is_ship=function(v) return isclass(v,'ship') end,
  context=function(v,class,include_self) local result=context(v,class,include_self);if result==0 then return nil end;return result end,
  controlled=function() local v=controlled();if v==0 then return false end;return v end,
  occupied=function() local v=occupied();if v==0 then return false end;return v end,
  player_container=function() local v=container();if v==0 then return nil end;return v end,
  -- GetComponentData is an X4 Lua API, unlike the FFI calls above. It expects
  -- a Lua component ID, not a uint64 cdata value. Keep the decimal string
  -- exact; converting through a Lua number would round IDs above 2^53.
  dock_state=function(v)
   local decimal=(tostring(v):gsub('ULL$',''))
   assert(decimal:match('^%d+$') and decimal~='0', 'invalid component ID')
   local id=assert(ConvertStringToLuaID(decimal), 'component ID conversion failed')
   return GetComponentData(id,'isdocked','isdocking','isinternallystored')
  end,
  pose=function(v) local p=position(v);return {x=tonumber(p.x),y=tonumber(p.y),z=tonumber(p.z),
   yaw=tonumber(p.yaw),pitch=tonumber(p.pitch),roll=tonumber(p.roll)} end,
  set_pose=function(v,s,p) set_position(v,s,ffi.new('UIPosRot',p)) end,
 }
end

-- expected_save_path is provided out of band by the harness, not a network
-- peer. attest_private_profile(path,snapshot_sha) must confirm this exact
-- isolated sandbox and the currently loaded verified snapshot;
-- a 45841 suffix alone is not proof. prove_direct_parent(...) must establish
-- the exact native parent (a zone ancestor alone is not enough), and
-- prove_no_other_player(...) must rule out any other player representation.
-- prove_clearance(...) must independently establish safe placement; current
-- angles are radians and proposed setter angles are degrees. Test bindings
-- exist only to unit-test this module.
-- `actor` and `sector` are locally enrolled handles from one verified snapshot.
function M.new(options)
 assert(type(options)=='table' and options.enabled==true,'explicit experiment required')
 local cfg,gate,apply=options.cfg,options.gate,options.pose_apply
 assert(type(cfg)=='table' and cfg.test_profile=='45841' and cfg.slot=='p2'
  and cfg.native_gate_fixture_pose_experiment==true, 'isolated guest diagnostic required')
 assert(type(cfg.native_gate_snapshot_fixture)=='table' and #cfg.native_gate_snapshot_fixture==12
  and saved_id(cfg.native_gate_snapshot_fixture[1]), 'saved fixture identity required')
 assert(type(options.expected_snapshot_sha)=='string' and #options.expected_snapshot_sha==64
  and options.expected_snapshot_sha:match('^[0-9a-f]+$')
  and cfg.native_gate_snapshot_sha==options.expected_snapshot_sha, 'verified snapshot pin required')
 assert(type(gate)=='table' and type(gate.saved_identity)=='function', 'saved-identity bridge required')
 assert(type(apply)=='table' and type(apply.new)=='function', 'pose guard required')
 assert(type(options.expected_save_path)=='string' and options.expected_save_path:sub(1,1)=='/'
  and options.expected_save_path:sub(-#'/45841/save')=='/45841/save', 'exact private save path required')
 assert(type(options.attest_private_profile)=='function' and type(options.prove_clearance)=='function'
  and type(options.prove_direct_parent)=='function' and type(options.prove_no_other_player)=='function',
  'private profile, parent, player and clearance attestations required')
 assert(saved_id(options.expected_sector_saved), 'saved sector identity required')
 local api=options.test_api or native_api()
 local fixture,sector=api.normalize(options.actor),api.normalize(options.sector)
 local expected_fixture,expected_sector=cfg.native_gate_snapshot_fixture[1],options.expected_sector_saved
 local function key(v) return api.key(v) end
 local fixture_key,sector_key=key(fixture),key(sector)
 assert(fixture_key~='' and sector_key~='', 'local fixture handles required')
 local function identity(v) return gate.saved_identity(key(v)) end
 local function private_profile()
  local p=api.path()
  return p==options.expected_save_path and options.attest_private_profile(p,options.expected_snapshot_sha)==true
 end
 assert(private_profile(), 'private profile not established')
 assert(api.valid(fixture)==true and api.operational(fixture)==true and api.is_ship(fixture)==true,
  'fixture unavailable')
 assert(identity(fixture)==expected_fixture and identity(sector)==expected_sector,'saved identity mismatch')
 assert(options.prove_no_other_player(fixture)==true, 'other player exclusion unproven')
 assert(key(api.context(fixture,'sector',false))==sector_key,'fixture outside expected sector')
 local zone=api.context(fixture,'zone',false)
 local zone_key=key(zone);assert(zone_key~='', 'fixture zone unavailable')
 assert(options.prove_direct_parent(fixture,zone)==true, 'fixture direct parent unproven')

 local function player_ship_or_station()
  local player=api.player_container()
  if player==nil or api.valid(player)~=true then return nil end
  if api.is_ship(player)==true then return player end
  local ship=api.context(player,'ship',true)
  if ship then return ship end
  -- A validated station context establishes a non-ship location. Unknown
  -- containment (including space-suit or missing context) fails closed.
  local station=api.context(player,'station',true)
  if station and api.valid(station)==true then return false end
  return nil
 end
 local engine={}
 engine.key=key
 engine.isolated=function() return private_profile() and options.prove_no_other_player(fixture)==true end
 engine.operational=function(v) return api.valid(v)==true and api.operational(v)==true end
 engine.is_ship=api.is_ship
 engine.controlled_ship=api.controlled
 engine.occupied_ship=api.occupied
 engine.player_container=player_ship_or_station
 engine.sector=function(v)
  if key(api.context(v,'zone',false))~=zone_key then return nil end
  if options.prove_direct_parent(v,zone)~=true then return nil end
  return api.context(v,'sector',false)
 end
 engine.dock_state=api.dock_state
 engine.container=function(v) return api.context(v,'container',false) or false end
 engine.pose=api.pose
 local function guard_again()
  assert(engine.isolated() and engine.operational(fixture) and engine.is_ship(fixture), 'fixture or profile changed')
  assert(identity(fixture)==expected_fixture and identity(sector)==expected_sector, 'saved identity changed')
  assert(key(engine.sector(fixture))==sector_key, 'fixture parent changed')
  local docked,docking,stored=engine.dock_state(fixture)
  assert(docked==false and docking==false and stored==false and engine.container(fixture)==false, 'fixture not free')
  local function protect(v)
   assert(v~=nil and (v==false or key(v)~=fixture_key), 'player context unknown or selected')
  end
  protect(engine.controlled_ship());protect(engine.occupied_ship());protect(engine.player_container())
 end
 engine.set_pose=function(v,s,target)
  assert(key(v)==fixture_key and key(s)==sector_key, 'write target mismatch')
  local candidate=copy_pose(target)
  guard_again()
  local current=copy_pose(api.pose(fixture))
  -- A verifier may inspect but must not be able to alter the actual target.
  assert(options.prove_clearance(fixture,sector,copy_pose(current),copy_pose(candidate))==true, 'safe placement unproven')
  guard_again()
  -- X4 getter is conventionally read in radians; the historical setter uses
  -- degrees. The parent harness must validate this in a native nonzero-angle
  -- control before claiming correctness for this executable.
  api.set_pose(fixture,sector,candidate)
 end
 local identities={
  ship=function(v) if key(v)==fixture_key and identity(v)==expected_fixture then return 'test-only-fixture-1' end end,
  sector=function(v) if key(v)==sector_key and identity(v)==expected_sector then return expected_sector end end,
 }
 return apply.new(engine,identities,fixture,sector,
  {enabled=true,fixture_id='test-only-fixture-1',sector_id=expected_sector})
end
return M
