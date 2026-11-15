-- Explicitly enabled, read-only fixture diagnostic for the disposable Linux harness.
local M = {}
local attempted = false
function M.sample(cfg, tick, actors, log)
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
  local scanner = assert(X4LAN_AUTHORITY_SHIP_SCAN, 'scanner missing')
  local engine = assert(X4LAN_AUTHORITY_SHIP_ENGINE, 'engine adapter missing').new()
  local actor = assert(actors[1], 'fixture 1 unavailable')
  local fixture = ffi.new('UniverseID', actor)
  local fixture_key = engine.key(fixture)
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
