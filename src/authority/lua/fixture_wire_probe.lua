-- Disposable Linux diagnostic: read one enrolled fixture and exchange its pose.
-- Read-only unless the separate isolated one-shot wire-warp option is enabled.
-- All local configuration and endpoints are supplied by the runner.
local M={}
local wire, connection, engine, disabled, pinned_sector, warp, clock, warp_actor, warp_zone, ffi, C
function M.sample(cfg,tick,actors,log,gate)
 if cfg.native_gate_authority_wire ~= true or disabled or tick < 30 then return end
 local stage='initial'
 local ok = pcall(function()
  if not wire then
   stage='configuration'
   assert(cfg.test_profile=='45841' and (cfg.slot=='p1' or cfg.slot=='p2'))
   assert(type(cfg.native_gate_authority_wire_port)=='number' and cfg.native_gate_authority_wire_port%1==0
    and cfg.native_gate_authority_wire_port>=1 and cfg.native_gate_authority_wire_port<=65535)
   local role=cfg.slot=='p1' and 'SOURCE' or 'GUEST'
   stage='network_open'
   local net=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
   connection=net.open('127.0.0.1',cfg.native_gate_authority_wire_port)
   wire=assert(X4LAN_AUTHORITY_FIXTURE_WIRE).new(connection,role,cfg.native_gate_authority_wire_lease,'test-only-fixture-1')
   if role=='SOURCE' or cfg.native_gate_authority_wire_warp then engine=assert(X4LAN_AUTHORITY_SHIP_ENGINE).new() end
   if cfg.native_gate_authority_wire_warp then
    stage='warp_configuration'
    assert(type(gate.saved_identity)=='function' and #cfg.native_gate_snapshot_fixture==12)
    assert(type(cfg.native_gate_authority_warp_sector)=='string' and #cfg.native_gate_authority_warp_sector==16)
    clock=assert(net.monotonic)
    ffi=require('ffi');C=ffi.C
    ffi.cdef[[bool IsValidComponent(UniverseID);UniverseID GetPlayerControlledShipID(void);
     UniverseID GetPlayerOccupiedShipID(void);UniverseID GetPlayerContainerID(void);]]
   end
  end
  local position
  local function guarded_pose()
   stage='actor_validity'
   local ship=ffi.new('UniverseID',assert(actors[1]));local key=engine.key(ship)
   assert(C.IsValidComponent(ship) and engine.operational(ship) and engine.is_ship(ship))
   stage='actor_identity'
   assert(gate.saved_identity((tostring(ship):gsub('ULL$','')))==cfg.native_gate_snapshot_fixture[1])
   stage='sector_identity'
   local sector=assert(engine.sector(ship));local sector_key=engine.key(sector)
   assert(gate.saved_identity((tostring(sector):gsub('ULL$','')))==cfg.native_gate_authority_warp_sector)
   stage='zone'
   local zone=C.GetContextByClass(ship,'zone',false);local zone_key=engine.key(zone);assert(zone_key~='')
   if warp_actor then assert(warp_actor==key and warp_zone==zone_key and pinned_sector==sector_key)
   else warp_actor,warp_zone,pinned_sector=key,zone_key,sector_key end
   stage='player_context'
   for _,v in ipairs({C.GetPlayerControlledShipID(),C.GetPlayerOccupiedShipID(),C.GetPlayerContainerID()}) do
    assert(engine.key(v)~=key)
   end
   local container=C.GetPlayerContainerID();assert(container~=0 and C.IsValidComponent(container))
   local context=C.GetContextByClass(container,'ship',true)
   if context~=0 then assert(engine.key(context)~=key)
   else assert(C.GetContextByClass(container,'station',true)~=0) end
   stage='dock_state'
   local luaid=ConvertStringToLuaID((key:gsub('ULL$','')))
   local docked,docking,stored=GetComponentData(luaid,'isdocked','isdocking','isinternallystored')
   assert(docked==false and docking==false and stored==false)
   stage='position'
   local p=engine.pose(ship)
   for _,v in ipairs({p.x,p.y,p.z}) do assert(v==v and v~=math.huge and v~=-math.huge) end
   return p,ship,sector,zone
  end
  if cfg.native_gate_authority_wire_warp and not warp then
   guarded_pose()
   stage='enrollment'
   local digest=assert(X4LAN_SHA256.digest)
   log('AUTHORITY_APPLY_ENROLL ship='..digest(cfg.native_gate_snapshot_fixture[1])..' sector='..digest(cfg.native_gate_authority_warp_sector))
   if cfg.slot=='p2' then
    warp=assert(X4LAN_AUTHORITY_FIXTURE_WIRE_WARP).new({
     read=guarded_pose,clock=clock,log=log,
     send=function(target)
      local _,ship,sector,zone=guarded_pose()
      local function id(v) return ConvertStringToLuaID((engine.key(v):gsub('ULL$',''))) end
      AddUITriggeredEvent('X4LAN_FixtureWarp','Once',{ship=id(ship),sector=id(sector),parent=id(zone),x=target.x,y=target.y,z=target.z})
     end})
    RegisterEvent('X4LAN_FixtureWarp.Result',function(_,value)
     local good=pcall(function() warp:ack(value) end)
     if not good then disabled=true;log('AUTHORITY_APPLY_ERROR') end
    end)
   else warp=true end
  end
  if cfg.native_gate_authority_wire_warp then guarded_pose() end
  if cfg.slot=='p1' then
   local ffi=require('ffi')
   local actor=assert(actors[1])
   local ship=ffi.new('UniverseID',actor)
   assert(engine.operational(ship) and engine.is_ship(ship))
   local sector=assert(engine.sector(ship));local key=engine.key(sector)
   if pinned_sector then assert(key==pinned_sector, 'fixture sector changed during wire test')
   else pinned_sector=key end
   position=engine.pose(ship)
   assert(engine.operational(ship))
   local after=engine.sector(ship);assert(after and engine.key(after)==key)
  end
  stage='wire_step'
  local before=wire.sent
  local received=wire:step(position)
  if cfg.slot=='p1' and wire.sent>before then
   log(string.format('AUTHORITY_WIRE_SOURCE tick=%d seq=%.0f x=%.17g y=%.17g z=%.17g',tick,wire.sent,position.x,position.y,position.z))
  elseif received then
   log(string.format('AUTHORITY_WIRE_RECEIVE tick=%d request=%.0f seq=%.0f x=%.17g y=%.17g z=%.17g',tick,received.request,received.source_sequence,received.x,received.y,received.z))
  end
  if cfg.native_gate_authority_wire_warp and cfg.slot=='p2' then stage='warp_sample';warp:sample(tick>=45 and received or nil) end
 end)
 if not ok then
  disabled=true
  if connection then pcall(function() connection:close() end) end
  -- Never include Lua error messages, raw handles or role leases in logs.
  local detail=cfg.native_gate_authority_wire_warp and (' stage='..stage) or ''
  log('AUTHORITY_WIRE_ERROR tick='..tostring(tick)..detail)
 end
end
X4LAN_AUTHORITY_FIXTURE_WIRE_PROBE=M
return M
