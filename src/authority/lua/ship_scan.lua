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

-- Optional local diagnostic; never invoked by scan(). A row represents each
-- distinct object returned by the faction enumerator, including unknown or
-- non-operational entries. The caller must provide read-only identity callbacks: they may use
-- sealed identity tables, but must not dereference an unverified component.
-- Supplied IDs are scoped labels, not validated cross-client identities. Rows
-- and status counts refer to distinct local objects; enumerated and memberships
-- count list entries. Repeated memberships do not imply their semantics.
local function inventory(engine, identities, options)
 assert(type(engine)=='table' and type(identities)=='table', 'missing inventory dependencies')
 options=options or {}
 local checkpoint_fn=options.checkpoint or function() end
 assert(type(checkpoint_fn)=='function', 'checkpoint must be a function')
 local function checkpoint()
  if not pcall(checkpoint_fn) then fail('inventory checkpoint failed') end
 end
 local max_factions=integer(options.max_factions or 256,4096,'faction limit')
 local max_ships=integer(options.max_ships or 250000,1000000,'ship limit')
 local max_fleet=integer(options.max_fleet or max_ships,max_ships,'fleet limit')
 local max_memberships=integer(options.max_memberships or max_ships,1000000,'membership limit')
 local scope=id(options.identity_scope,'identity scope')
 assert(type(identities.ship)=='function' and type(identities.sector)=='function', 'identity callbacks required')
 assert(options.on_duplicate==nil or type(options.on_duplicate)=='function', 'invalid duplicate diagnostic')
 local function call(fn, ...)
  if type(fn)~='function' then return false end
  return pcall(fn,...)
 end
 local function stable_id(fn, value)
  local ok, result=call(fn,value)
  if not ok or type(result)~='string' or result=='' or #result>256 then return nil end
  return result
 end
 local function object_key(object)
  local ok, key=call(engine.key,object)
  if not ok or type(key)~='string' or key=='' or #key>256 then fail('inventory local object key unavailable') end
  return key
 end
 local function bool(fn, value)
  local ok, result=call(fn,value)
  if not ok or type(result)~='boolean' then return nil end
  return result
 end
 local function factions()
  checkpoint()
  local ok, values, truncated=call(engine.factions,max_factions)
  checkpoint()
  if not ok or truncated or type(values)~='table' or #values==0 or #values>=max_factions then fail('inventory faction enumeration incomplete') end
  local seen={}
  for _, faction in ipairs(values) do
   id(faction,'faction'); if seen[faction] then fail('inventory duplicate faction') end
   seen[faction]=true
  end
  return values,seen
 end
 local function fleet(faction)
  checkpoint()
  local ok, before=call(engine.fleet_count,faction)
  if not ok or type(before)~='number' or before<0 or before~=math.floor(before) or before>max_fleet then fail('inventory invalid fleet count') end
  local got, ships, truncated=call(engine.fleet,faction,before+1)
  checkpoint()
  local again, count=call(engine.fleet_count,faction)
  if not got or truncated or type(ships)~='table' or #ships~=before or not again or count~=before then fail('inventory fleet enumeration changed or incomplete') end
  return ships
 end
 local rows, membership, ids, reasons={},{},{},{}
 local counts={enumerated=0,memberships=0,objects=0,repeated_memberships=0,position_observed=0,not_confirmed_operational=0,unavailable=0,unresolved_identity=0}
 local first_factions,first_set=factions()
 for faction_index,faction in ipairs(first_factions) do
  for ship_index,ship in ipairs(fleet(faction)) do
   checkpoint()
   counts.memberships=counts.memberships+1
   counts.enumerated=counts.enumerated+1
   if counts.memberships>max_memberships then fail('inventory membership limit exceeded') end
   local key=object_key(ship)
   local previous=membership[key]
   if previous then
    if previous.ship~=ship then fail('inventory local object key collision') end
    local first=previous.factions[faction]
    if first then
     if options.on_duplicate then pcall(options.on_duplicate,faction,first.ship_index,faction,ship_index,ship) end
     fail(string.format('inventory duplicate object first=%d:%d repeated=%d:%d',
      first.faction_index,first.ship_index,faction_index,ship_index))
    end
    if stable_id(identities.ship,ship)~=previous.identity or bool(engine.operational,ship)~=previous.operational then
     fail('inventory identity or operational state changed')
    end
    counts.repeated_memberships=counts.repeated_memberships+1
    previous.factions[faction]={faction_index=faction_index,ship_index=ship_index}
    previous.row.memberships[#previous.row.memberships+1]=faction
   else
    if #rows>=max_ships then fail('inventory ship limit exceeded') end
    local sid=stable_id(identities.ship,ship)
    if sid and ids[sid] then fail('inventory duplicate supplied identity') end
    if sid then ids[sid]=key else counts.unresolved_identity=counts.unresolved_identity+1 end
    local record={ship=ship,
     factions={[faction]={faction_index=faction_index,ship_index=ship_index}},identity=sid,operational=bool(engine.operational,ship)}
    membership[key]=record
    local row={ordinal=#rows+1, identity=sid, status='unavailable',memberships={faction}}
    record.row=row
    if record.operational==false then
     row.status='not_confirmed_operational'
    elseif record.operational==nil then
     row.reason='operational_unknown'
    else
     record.ship_class=bool(engine.is_ship,ship)
     if record.ship_class~=true then
      row.reason=record.ship_class==false and 'ship_class_not_confirmed' or 'ship_class_unknown'
     else
      local ok, sector=call(engine.sector,ship)
      if ok and sector then record.sector_key=object_key(sector);record.sector_identity=stable_id(identities.sector,sector) end
      if not ok or not sector then row.reason='sector_unavailable'
      elseif not sid then row.reason='ship_identity_unavailable'
      elseif not record.sector_identity then row.reason='sector_identity_unavailable'
      else
       local pose_ok, p=call(engine.pose,ship)
       local pose={}
       if pose_ok and type(p)=='table' then
        for _,field in ipairs({'x','y','z','yaw','pitch','roll'}) do if not finite(p[field]) then pose_ok=false;break end;pose[field]=p[field] end
       else pose_ok=false end
       if pose_ok then row.status='position_observed';row.sector=record.sector_identity;row.pose=pose
       else row.reason='pose_unavailable' end
      end
     end
    end
    counts.objects=counts.objects+1
    counts[row.status]=counts[row.status]+1
    if row.reason then reasons[row.reason]=(reasons[row.reason] or 0)+1 end
    rows[#rows+1]=row
   end
  end
 end
 local last_factions,last_set=factions()
 for f in pairs(first_set) do if not last_set[f] then fail('inventory faction membership changed') end end
 for f in pairs(last_set) do if not first_set[f] then fail('inventory faction membership changed') end end
 for _,faction in ipairs(last_factions) do
  for _,ship in ipairs(fleet(faction)) do
   checkpoint()
   local key=object_key(ship)
   local record=membership[key]
   if not record or not record.factions[faction] then fail('inventory object membership changed') end
   if record.ship~=ship then fail('inventory local object key collision') end
   if stable_id(identities.ship,ship)~=record.identity or bool(engine.operational,ship)~=record.operational then fail('inventory identity or operational state changed') end
   if record.operational==true then
    if bool(engine.is_ship,ship)~=record.ship_class then fail('inventory class state changed') end
    if record.ship_class==true then
     local ok, sector=call(engine.sector,ship)
     local key_after=ok and sector and object_key(sector) or nil
     local identity_after=ok and sector and stable_id(identities.sector,sector) or nil
     if key_after~=record.sector_key or identity_after~=record.sector_identity then fail('inventory sector state changed') end
    end
   end
   record.factions[faction]=nil
   if not next(record.factions) then membership[key]=nil end
  end
 end
 if next(membership) then fail('inventory object membership changed') end
 return {rows=rows, counts=counts, unavailable_reasons=reasons, identity_scope=scope,
  enumeration='faction_lists_rechecked_non_atomic', universe_coverage='unknown', positions_complete=false}
end

function M.inventory(engine, identities, options)
 local ok,result=pcall(inventory,engine,identities,options)
 if not ok then return nil,'inventory failed: '..tostring(result) end
 return result
end


-- Cooperative processing: resume only at scanner checkpoints. Each individual
-- engine call (including full native fleet enumeration and adapter conversion)
-- remains synchronous and cannot be preempted by this mechanism. Never expose
-- rows until both non-atomic enumeration passes have completed successfully.
function M.inventory_task(engine, identities, options)
 options=options or {}
 local copied={}
 for k,v in pairs(options) do copied[k]=v end
 local original=copied.checkpoint
 assert(original==nil or type(original)=='function', 'checkpoint must be a function')
 copied.checkpoint=function()
  if original then original() end
  coroutine.yield()
 end
 local thread=coroutine.create(function() return M.inventory(engine,identities,copied) end)
 local finished=false
 return {
  step=function(max_checkpoints, should_yield)
   if finished then return 'error',nil,'inventory task already finished' end
   if type(max_checkpoints)~='number' or max_checkpoints~=math.floor(max_checkpoints) or max_checkpoints<1 or
      type(should_yield)~='function' then
    finished=true;return 'error',nil,'invalid inventory task budget'
   end
   for _=1,max_checkpoints do
    local ok,result,why=coroutine.resume(thread)
    if not ok then finished=true;return 'error',nil,'inventory task failed' end
    if coroutine.status(thread)=='dead' then
     finished=true
     if result then return 'complete',result end
     return 'error',nil,why
    end
    local checked,stop=pcall(should_yield)
    if not checked or type(stop)~='boolean' then
     finished=true;return 'error',nil,'inventory task clock failed'
    end
    if stop then break end
   end
   return 'running'
  end,
 }
end

X4LAN_AUTHORITY_SHIP_SCAN = M
return M
