-- Isolated one-ship Linux X4 diagnostic, not a gameplay adapter.
-- The harness must serialize this module's Validate request and call verified
-- or refused for exactly its outstanding event; the result has no request ID.
-- Its raw native setter has NO independent collision-clearance proof. The
-- caller must ensure disposable profiles, no other player and clean teardown;
-- the designated test area and placement are not proved collision-free.
local M={}
function M.new(o)
 assert(type(o)=='table' and o.enabled==true and (o.role=='SOURCE' or o.role=='GUEST'))
 assert(type(o.expected_path)=='string' and o.expected_path:sub(1,1)=='/' and o.expected_path:sub(-11)=='/45841/save')
 assert(type(o.actor)=='cdata' and type(o.frame)=='string' and type(o.epoch)=='string' and type(o.index)=='number')
 assert(type(o.probe_module)=='table' and type(o.probe_module.new)=='function')
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
 ffi.cdef[[
 const char* GetSaveFolderPath(void); bool IsGamePaused(void); bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID); bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);
 UniverseID GetPlayerControlledShipID(void); UniverseID GetPlayerOccupiedShipID(void);
 UniverseID GetPlayerContainerID(void); UIPosRot GetObjectPositionInSector(UniverseID);
 void SetObjectSectorPos(UniverseID,UniverseID,UIPosRot);
 ]]
 local C=ffi.C
 local actor=ffi.new('UniverseID',o.actor)
 local function key(v) if v==nil or v==0 then return '' end return (tostring(v):gsub('ULL$','')) end
 local actor_key=key(actor);assert(actor_key~='')
 local sector_key,zone_key,sector
 local pending,confirmed,stopped=false,false,false
 local probe
 local function local_guard(a,epoch,index,frame)
  if not confirmed or stopped or key(a)~=actor_key or epoch~=o.epoch or index~=o.index or frame~=o.frame then return false end
  if not C.IsGamePaused() then return false end
  local path=C.GetSaveFolderPath()
  if path==nil or path==ffi.NULL or ffi.string(path):gsub('\\','/'):gsub('/+$','')~=o.expected_path then return false end
  if not C.IsValidComponent(actor) or not C.IsComponentOperational(actor) or not C.IsComponentClass(actor,'ship') then return false end
  local s=C.GetContextByClass(actor,'sector',false);local z=C.GetContextByClass(actor,'zone',false)
  local sk,zk=key(s),key(z)
  if sk=='' or zk=='' then return false end
  if sector_key and (sector_key~=sk or zone_key~=zk) then return false end
  sector,sector_key,zone_key=s,sk,zk
  local controlled,occupied,container=C.GetPlayerControlledShipID(),C.GetPlayerOccupiedShipID(),C.GetPlayerContainerID()
  for _,v in ipairs({controlled,occupied,container}) do if key(v)==actor_key then return false end end
  if key(container)=='' or not C.IsValidComponent(container) then return false end
  local pship=C.GetContextByClass(container,'ship',true)
  if key(pship)~='' then if key(pship)==actor_key then return false end
  elseif key(C.GetContextByClass(container,'station',true))=='' then return false end
  local id=ConvertStringToLuaID(actor_key)
  local docked,docking,stored=GetComponentData(id,'isdocked','isdocking','isinternallystored')
  return docked==false and docking==false and stored==false
 end
 local function request(epoch,index)
  assert(not pending and not stopped and C.IsGamePaused(),'game is not paused');pending=true
  AddUITriggeredEvent('X4AuthorityRegistryMotionGuard','Validate',{epoch=epoch,index=index,frame=o.frame})
 end
 local function read(a)
  assert(local_guard(a,o.epoch,o.index,o.frame))
  local p=C.GetObjectPositionInSector(actor)
  local result={x=tonumber(p.x),y=tonumber(p.y),z=tonumber(p.z),yaw=tonumber(p.yaw),pitch=tonumber(p.pitch),roll=tonumber(p.roll)}
  for _,v in pairs(result) do assert(type(v)=='number' and v==v and math.abs(v)<math.huge,'invalid native pose') end
  return result
 end
 local function write(a,frame,target)
  assert(o.role=='GUEST' and local_guard(a,o.epoch,o.index,frame))
  local before=read(a)
  local deg=180/math.pi
  assert(local_guard(a,o.epoch,o.index,frame),'pause or safety guard lost')
  -- Diagnostic setter intentionally matches the earlier continuous fixture;
  -- no proof exists for nonzero-angle conversion or collision clearance.
  C.SetObjectSectorPos(actor,sector,ffi.new('UIPosRot',{x=target.x,y=target.y,z=target.z,
    yaw=before.yaw*deg,pitch=before.pitch*deg,roll=before.roll*deg}))
 end
 probe=o.probe_module.new({enabled=true,role=o.role,epoch=o.epoch,index=o.index,frame=o.frame,
  transport=o.transport,lease=o.lease,wire_module=o.wire_module,continuous_module=o.continuous_module,
  resolve=request,validate=local_guard,read=read,write=write,clock=o.clock,log=o.log})
 local bound=false
 local last_nudge,nudges=nil,0
 local api={}
 function api:verified(value)
  local valid,observed=pcall(function() return key(ffi.new('UniverseID',ConvertIDTo64Bit(value))) end)
  if stopped or not pending or not valid or observed~=actor_key then self:stop();error('unexpected MD guard response') end
  pending=false;confirmed=true
  local ok,err=pcall(function()
   if not bound then probe:bind(o.epoch,o.index,actor);bound=true end
   probe:step()
   if o.role=='SOURCE' and o.test_nudge==true and nudges<20 then
    local now=o.clock();assert(type(now)=='number' and now==now and math.abs(now)<math.huge)
    if not last_nudge or now-last_nudge>=.25 then
     assert(local_guard(actor,o.epoch,o.index,o.frame))
     local before=read(actor);local deg=180/math.pi
     assert(local_guard(actor,o.epoch,o.index,o.frame),'pause or safety guard lost')
     C.SetObjectSectorPos(actor,sector,ffi.new('UIPosRot',{x=before.x+5,y=before.y,z=before.z,
      yaw=before.yaw*deg,pitch=before.pitch*deg,roll=before.roll*deg}))
     nudges=nudges+1;last_nudge=now
     o.log(('REGISTRY_MOTION_NUDGE number=%d before_x=%.17g target_x=%.17g'):format(nudges,before.x,before.x+5))
    end
   end
  end)
  confirmed=false
  if not ok then self:stop();error(err) end
 end
 function api:refused() self:stop();error('MD guard refused') end
 function api:tick()
  if not stopped and not C.IsGamePaused() then self:stop();error('game is not paused') end
  if not stopped and not pending then
   local ok,err=pcall(request,o.epoch,o.index)
   if not ok then self:stop();error(err) end
  end
 end
 function api:stop() stopped=true;pending=false;confirmed=false;if probe then probe:stop() end end
 return api
end
X4LAN_AUTHORITY_REGISTRY_MOTION_NATIVE=M
return M
