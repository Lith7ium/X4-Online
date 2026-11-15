-- Explicitly enabled, read-only fixture diagnostic for the disposable Linux harness.
local M = {}
local attempted = false
function M.sample(cfg, tick, actors, log, gate)
 if not cfg.native_gate_authority_scan or attempted or tick < 30 then return end
 attempted = true
 local ok, err = pcall(function()
  assert(cfg.native_gate_authority_scan == true, 'explicit boolean required')
  assert(cfg.native_gate_hash == 'battle' and cfg.native_gate_snapshot_fixture and
   #cfg.native_gate_snapshot_fixture == 12, 'saved battle fixture required')
  local ffi = require('ffi')
  ffi.cdef[[const char* GetSaveFolderPath(void);]]
  local path = ffi.string(ffi.C.GetSaveFolderPath()):gsub('\\','/'):gsub('/+$','')
  assert(cfg.test_profile=='45841' and path:sub(-#'/45841/save')=='/45841/save', 'isolated profile required')
  local engine = assert(X4LAN_AUTHORITY_SHIP_ENGINE, 'engine adapter missing').new()
  local actor = assert(actors[1], 'fixture 1 unavailable')
  local fixture = ffi.new('UniverseID', actor)
  local fixture_key = engine.key(fixture)
  -- This read is independent of the fleet census. Only the enrolled fixture
  -- is queried; never call a position getter on an unknown failed fleet entry.
  local read_ok, read_error = pcall(function()
   assert(engine.operational(fixture), 'fixture not operational')
   assert(engine.is_ship(fixture), 'fixture is not a ship')
   local parent=assert(engine.sector(fixture), 'fixture sector unavailable')
   local parent_key=engine.key(parent)
   local p=engine.pose(fixture)
   for _, name in ipairs({'x','y','z','yaw','pitch','roll'}) do
    local v=p[name]
    assert(type(v)=='number' and v==v and v~=math.huge and v~=-math.huge, 'invalid fixture pose')
   end
   assert(engine.operational(fixture), 'fixture no longer operational')
   local after=engine.sector(fixture)
   assert(after and engine.key(after)==parent_key, 'fixture sector changed')
   log(string.format('AUTHORITY_FIXTURE_READ tick=%d identity=test-only-fixture-1 operational=1 sector_present=1 x=%.9g y=%.9g z=%.9g yaw=%.9g pitch=%.9g roll=%.9g',
    tick,p.x,p.y,p.z,p.yaw,p.pitch,p.roll))
  end)
  if not read_ok then log('AUTHORITY_FIXTURE_ERROR tick='..tostring(tick)..' why='..tostring(read_error):gsub('[\r\n]',' '):sub(1,300)) end
  local scanner = assert(X4LAN_AUTHORITY_SHIP_SCAN, 'scanner missing')
  local ship_ids, sector_ids, next_ship, next_sector = {}, {}, 0, 0
  local identities = {
   ship=function(ship)
    local key=engine.key(ship)
    if key==fixture_key then return 'test-only-fixture-1' end
    if not ship_ids[key] then next_ship=next_ship+1; ship_ids[key]='test-only-ship-'..next_ship end
    return ship_ids[key]
   end,
   sector=function(sector)
    local key=engine.key(sector)
    if not sector_ids[key] then next_sector=next_sector+1; sector_ids[key]='test-only-sector-'..next_sector end
    return sector_ids[key]
   end,
  }
  assert(type(GetCurRealTime)=='function', 'real-time clock unavailable')
  local started=GetCurRealTime()
  assert(type(started)=='number' and started==started and started~=math.huge and started~=-math.huge, 'invalid real-time clock')
  local result, why = scanner.scan(engine, identities, {max_factions=1024, max_ships=4096, max_fleet=4096,
   on_nonoperational=function(ship, faction_index, ship_index, recheck_membership)
    -- This runs only in the isolated, explicitly enabled fixture probe. Check
    -- the same faction membership again before any additional component call.
    local valid_ok, valid = pcall(engine.operational, ship)
    local status = valid_ok and type(valid)=='boolean' and (valid and 'true' or 'false') or 'unknown'
    local member_ok, member = pcall(recheck_membership)
    local membership = member_ok and type(member)=='boolean' and (member and 'true' or 'false') or 'unknown'
    local exists, construction, shipclass, wreck_ui, saved = 'unknown', 'unknown', 'unknown', 'unknown', 'unknown'
    if membership=='true' then
     -- Native X4's IsValidComponent shares IsComponentOperational's index and
     -- generation checks; X4's own UI declares this same uint64 signature.
     if type(engine.valid)=='function' then
      local ok_valid, value=pcall(engine.valid,ship)
      if ok_valid and type(value)=='boolean' then exists=value and 'true' or 'false' end
     end
     -- The identity lookup uses the gate's private runtime-to-save table, not
     -- a component dereference. Its result is written only to this isolated
     -- profile's diagnostic log and must not be published.
     if type(gate)=='table' and type(gate.saved_identity)=='function' then
      local decimal=tostring(ship):gsub('ULL$','')
      if decimal:match('^%d+$') then
       local ok_saved, value=pcall(gate.saved_identity,decimal)
       if ok_saved and type(value)=='string' and value:match('^[0-9a-f]+$') and #value==16 and value~='0000000000000000' then saved=value end
      end
     end
     -- Follow the order used by X4's UI: only a valid component can be queried
     -- for class/construction. Do not infer wreck from operational=false alone.
     if exists=='true' then
      local ok_class, value=pcall(engine.is_ship,ship)
      if ok_class and type(value)=='boolean' then shipclass=value and 'true' or 'false' end
      if type(IsComponentConstruction)=='function' and type(ConvertStringTo64Bit)=='function' then
       local ok_construction, value=pcall(function() return IsComponentConstruction(ConvertStringTo64Bit(tostring(ship))) end)
       if ok_construction and type(value)=='boolean' then construction=value and 'true' or 'false' end
      end
      if status=='false' and shipclass=='true' and construction=='false' then wreck_ui='true'
      elseif status=='true' or shipclass=='false' or construction=='true' then wreck_ui='false' end
     end
    end
    log(string.format('AUTHORITY_NONOP_DIAG tick=%d faction_index=%d ship_index=%d operational_recheck=%s same_fleet_recheck=%s valid=%s construction=%s ship_class=%s wreck_ui=%s saved_private=%s',
     tick,faction_index,ship_index,status,membership,exists,construction,shipclass,wreck_ui,saved))
   end,
   checkpoint=function()
    local now=GetCurRealTime()
    assert(type(now)=='number' and now==now and now>=started and now-started<=2, 'scan time budget exceeded')
   end})
  assert(result, why)
  local selected
  for _, row in ipairs(result.rows) do if row.id=='test-only-fixture-1' then selected=row end end
  assert(selected, 'fixture 1 absent from enumerated ships')
  -- Independent getter call; no claim of a simultaneous snapshot or transport.
  assert(engine.operational(fixture), 'fixture lost before readback')
  local parent=engine.sector(fixture)
  assert(parent and identities.sector(parent)==selected.sector, 'fixture parent changed before readback')
  local actual=engine.pose(fixture)
  local p=selected.pose
  for _, f in ipairs({'x','y','z','yaw','pitch','roll'}) do
   local v=actual[f]; assert(type(v)=='number' and v==v and v~=math.huge and v~=-math.huge, 'invalid fixture readback')
  end
  log(string.format('AUTHORITY_SCAN_FIXTURE tick=%d identity=test-only-fixture-1 sector=%s ships=%d consistency=%s x=%.9g y=%.9g z=%.9g yaw=%.9g pitch=%.9g roll=%.9g read_x=%.9g read_y=%.9g read_z=%.9g read_yaw=%.9g read_pitch=%.9g read_roll=%.9g',
   tick,selected.sector,#result.rows,result.consistency,p.x,p.y,p.z,p.yaw,p.pitch,p.roll,actual.x,actual.y,actual.z,actual.yaw,actual.pitch,actual.roll))
 end)
 if not ok then log('AUTHORITY_SCAN_ERROR tick='..tostring(tick)..' why='..tostring(err):gsub('[\r\n]',' '):sub(1,300)) end
end
X4LAN_AUTHORITY_FIXTURE_SCAN_PROBE = M
return M
