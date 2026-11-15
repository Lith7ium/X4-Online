-- Explicit disposable Linux fixture experiment; all game object calls are reads.
local M={}
local wire, connection, engine, clock, disabled, enrolled
local clock_phase
local keys, sectors, frames = {}, {}, {}
local function id(i) return string.format('fixture-%02d',i) end
function M.sample(cfg,tick,actors,log,gate)
 if cfg.native_gate_authority_fleet~=true or disabled or tick<30 then return end
 -- Only fixed stage names and the ordinal of the enrolled test fixture are
 -- logged. Exceptions, native handles, saved identities and leases stay private.
 local stage, ordinal='configuration',0
 local ok=pcall(function()
  if not wire then
   assert(cfg.test_profile=='45841' and (cfg.slot=='p1' or cfg.slot=='p2'))
   assert(type(gate.saved_identity)=='function' and #cfg.native_gate_snapshot_fixture==12)
   stage='transport_initial'
   local net=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
   stage='clock_symbol'
   local monotonic=assert(net.monotonic)
   assert(type(monotonic)=='function')
   local last_clock
   clock=function()
    clock_phase='clock_call'
    local value=monotonic()
    clock_phase='clock_value'
    assert(type(value)=='number' and value>=0 and value==value and value<math.huge)
    clock_phase='clock_regression'
    assert(not last_clock or value>=last_clock)
    last_clock=value
    clock_phase=nil
    return value
   end
   stage='clock_initial'
   clock() -- no weaker clock substitution if CLOCK_MONOTONIC is unavailable
   stage='engine_initial'
   engine=assert(X4LAN_AUTHORITY_SHIP_ENGINE).new()
   for i=1,12 do frames[id(i)]='test-frame' end
   stage='transport_initial'
   connection=net.open('127.0.0.1',cfg.native_gate_authority_fleet_port)
   stage='wire_initial'
   wire=assert(X4LAN_AUTHORITY_FIXTURE_FLEET_WIRE).new(connection,
    cfg.slot=='p1' and 'SOURCE' or 'GUEST1',cfg.native_gate_authority_fleet_lease,frames,1)
  end
  local ffi=require('ffi')
  local samples, sampled={},{},{}
  for i=1,12 do
   ordinal=i
   stage='actor_handle'
   local actor=assert(actors[i]); local ship=ffi.new('UniverseID',actor)
   local key=assert(engine.key(ship)); assert(key~='')
   stage='actor_saved_lookup'
   local saved=assert(gate.saved_identity(tostring(ship):gsub('ULL$','')))
   stage='actor_saved_match'
   assert(saved==cfg.native_gate_snapshot_fixture[i])
   stage='actor_liveness'
   if keys[i] then assert(keys[i]==key) else keys[i]=key end
   assert(engine.operational(ship) and engine.is_ship(ship))
   stage='sector_handle'
   local sector=assert(engine.sector(ship));local sector_key=assert(engine.key(sector))
   if i>1 then assert(sector_key==sectors[1], 'fixtures do not share the test sector') end
   stage='sector_saved_lookup'
   local sector_saved=assert(gate.saved_identity(tostring(sector):gsub('ULL$','')))
   stage='sector_saved_validate'
   assert(type(sector_saved)=='string' and sector_saved:match('^[0-9a-f]+$') and #sector_saved==16 and sector_saved~='0000000000000000')
   stage='sector_pinned'
   if sectors[i] then assert(sectors[i]==sector_key) else sectors[i]=sector_key end
   stage='sample_clock'
   local timestamp=clock()
   stage='sample_position'
   local p=engine.pose(ship)
   stage='sample_recheck'
   assert(engine.operational(ship)); local after=assert(engine.sector(ship)); assert(engine.key(after)==sector_key)
   samples[id(i)]=p; sampled[id(i)]=timestamp
   if not enrolled then
    stage='sector_digest'
    local hash=assert(X4LAN_SHA256.digest(sector_saved))
    assert(type(hash)=='string' and hash:match('^[0-9a-f]+$') and #hash==64)
    log(string.format('AUTHORITY_FLEET_ENROLL tick=%d id=%s sector=%s',tick,id(i),hash))
   end
  end
  enrolled=true
  ordinal=0
  stage='wire_clock'
  local now=clock()
  stage='wire_step'
  local updates,sent=wire:step(cfg.slot=='p1' and samples or nil,now)
  if cfg.slot=='p1' then
   stage='source_receipts'
   for _,row in ipairs(sent) do
    local p=assert(samples[row.fixture])
    log(string.format('AUTHORITY_FLEET_SOURCE tick=%d id=%s seq=%.0f time=%.9f x=%.17g y=%.17g z=%.17g',tick,row.fixture,row.sequence,sampled[row.fixture],p.x,p.y,p.z))
   end
  else
   stage='guest_receipts'
   for _,row in ipairs(updates) do
    log(string.format('AUTHORITY_FLEET_RECEIVE tick=%d id=%s request=%.0f seq=%.0f time=%.9f x=%.17g y=%.17g z=%.17g',tick,row.fixture,row.request,row.source_sequence,now,row.x,row.y,row.z))
   end
  end
 end)
 if not ok then
  disabled=true
  if connection then pcall(function() connection:close() end) end
  if clock_phase then stage=clock_phase end
  log(string.format('AUTHORITY_FLEET_ERROR tick=%d stage=%s fixture=%d',tick,stage,ordinal))
 end
end
X4LAN_AUTHORITY_FIXTURE_FLEET_PROBE=M
return M
