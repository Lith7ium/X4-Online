-- Read-only ship census. No scan or engine call occurs until scan() is invoked.
-- Engine handles are only used locally; caller must supply portable identities.
local M = {}

local function fail(message) error('ship scan: ' .. message, 0) end
local function integer(n, limit, what)
 if type(n) ~= 'number' or n ~= math.floor(n) or n < 1 or n > limit then fail('invalid ' .. what) end
 return n
end
local function id(value, what)
 if type(value) ~= 'string' or value == '' or #value > 256 then fail('invalid ' .. what) end
 return value
end
local function finite(n)
 return type(n) == 'number' and n == n and n ~= math.huge and n ~= -math.huge
end
local function scan(engine, identities, options)
 assert(type(engine) == 'table' and type(identities) == 'table', 'missing engine or identities')
 options = options or {}
 local checkpoint = options.checkpoint or function() end
 assert(type(checkpoint) == 'function', 'checkpoint must be a function')
 assert(options.on_nonoperational == nil or type(options.on_nonoperational) == 'function', 'invalid diagnostic callback')
 checkpoint()
 local max_factions = integer(options.max_factions or 256, 4096, 'faction limit')
 local max_ships = integer(options.max_ships or 250000, 1000000, 'ship limit')
 local max_fleet = integer(options.max_fleet or max_ships, max_ships, 'fleet limit')
 assert(type(identities.ship) == 'function' and type(identities.sector) == 'function', 'identity callbacks required')
 local function factions()
  -- A full buffer is ambiguous; fail rather than assert completeness.
  checkpoint()
  local values, truncated, reported = engine.factions(max_factions)
  checkpoint()
  if truncated or type(values) ~= 'table' or #values == 0 or #values >= max_factions then
   -- The export's return may mean written entries rather than the total; do not
   -- describe it as the true faction count when the buffer is full.
   local count = type(reported) == 'number' and reported >= 0 and reported == math.floor(reported)
    and tostring(reported) or (type(values) == 'table' and tostring(#values) or 'unavailable')
   fail('faction enumeration incomplete returned=' .. count .. ' capacity=' .. max_factions)
  end
  local seen = {}
  for _, f in ipairs(values) do
   id(f, 'faction'); if seen[f] then fail('duplicate faction') end; seen[f] = true
  end
  return values, seen
 end
 local function fleet(faction)
  checkpoint()
  local before = engine.fleet_count(faction)
  if type(before) ~= 'number' or before < 0 or before ~= math.floor(before) or before > max_fleet then fail('invalid fleet count or limit exceeded') end
  -- Ask for one extra entry so a full buffer is never accepted as complete.
  local ships, truncated = engine.fleet(faction, before + 1)
  checkpoint()
  if truncated or type(ships) ~= 'table' or #ships ~= before or engine.fleet_count(faction) ~= before then fail('fleet enumeration changed or incomplete') end
  return ships
 end
 local first_factions, first_set = factions()
 local membership, rows, ids = {}, {}, {}
 for faction_index, faction in ipairs(first_factions) do
  local ships = fleet(faction)
  for ship_index, ship in ipairs(ships) do
   checkpoint()
   local key = id(engine.key(ship), 'local object key')
   if membership[key] then fail('duplicate ship handle') end
   if #rows >= max_ships then fail('ship limit exceeded') end
   membership[key] = faction
   local where = ' faction_index=' .. faction_index .. '/' .. #first_factions ..
    ' ship_index=' .. ship_index .. '/' .. #ships .. ' scanned=' .. #rows
   if not engine.operational(ship) then
    -- Optional private, read-only diagnostics must never turn an incomplete
    -- census into success or replace its original failure. The handle is
    -- process-local; it must not become a network identity or public log.
    if options.on_nonoperational then
     local function recheck_membership()
      local matches=0
      for _, candidate in ipairs(fleet(faction)) do
       checkpoint()
       if id(engine.key(candidate), 'local object key') == key then matches=matches+1 end
      end
      if matches > 1 then fail('duplicate ship handle during diagnostic') end
      return matches == 1
     end
     pcall(options.on_nonoperational, ship, faction_index, ship_index, recheck_membership)
    end
    fail('ship not operational' .. where)
   end
   if not engine.is_ship(ship) then fail('enumerated object not ship class' .. where) end
   local sector = engine.sector(ship)
   if not sector then fail('ship sector unavailable') end
   local sid = id(identities.ship(ship), 'portable ship identity')
   local parent = id(identities.sector(sector), 'portable sector identity')
   if ids[sid] then fail('duplicate portable ship identity') end
   ids[sid] = true
   local p = engine.pose(ship)
   if type(p) ~= 'table' then fail('pose unavailable') end
   local pose = {}
   for _, field in ipairs({'x','y','z','yaw','pitch','roll'}) do
    if not finite(p[field]) then fail('invalid pose ' .. field) end
    pose[field] = p[field]
   end
   if not engine.operational(ship) or engine.key(engine.sector(ship)) ~= engine.key(sector) then fail('ship changed while sampled') end
   rows[#rows+1] = {id=sid, sector=parent, pose=pose}
  end
 end
 local next_factions, next_set = factions()
 for f in pairs(first_set) do if not next_set[f] then fail('faction membership changed') end end
 for f in pairs(next_set) do if not first_set[f] then fail('faction membership changed') end end
 local remaining = {}
 for key, faction in pairs(membership) do remaining[key] = faction end
 for _, faction in ipairs(next_factions) do
  for _, ship in ipairs(fleet(faction)) do
   checkpoint()
   local key = id(engine.key(ship), 'local object key')
   if remaining[key] ~= faction then fail('ship membership changed') end
   remaining[key] = nil
  end
 end
 if next(remaining) then fail('ship membership changed') end
 return {rows=rows, consistency='membership_rechecked_non_atomic'}
end

-- A failed scan returns no partial rows.
function M.scan(engine, identities, options)
 local ok, result = pcall(scan, engine, identities, options)
 if not ok then return nil, tostring(result) end
 return result
end

X4LAN_AUTHORITY_SHIP_SCAN = M
return M
