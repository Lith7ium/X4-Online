-- Explicit disposable Linux fixture experiment; all game object calls are reads.
local M={}
local wire, connection, engine, clock, disabled, enrolled
local keys, sectors, frames = {}, {}, {}
local function id(i) return string.format('fixture-%02d',i) end
function M.sample(cfg,tick,actors,log,gate)
 if cfg.native_gate_authority_fleet~=true or disabled or tick<30 then return end
 local ok=pcall(function()
  if not wire then
   assert(cfg.test_profile=='45841' and (cfg.slot=='p1' or cfg.slot=='p2'))
   assert(type(gate.saved_identity)=='function' and #cfg.native_gate_snapshot_fixture==12)
   local ffi=require('ffi')
   ffi.cdef[[struct x4lan_fleet_timespec { long sec; long nsec; };
             int clock_gettime(int, struct x4lan_fleet_timespec*);]]
   local t=ffi.new('struct x4lan_fleet_timespec[1]')
   clock=function()
    assert(ffi.C.clock_gettime(1,t)==0)
    local value=tonumber(t[0].sec)+tonumber(t[0].nsec)/1000000000
    assert(value>=0 and value==value and value<math.huge)
    return value
   end
   clock() -- no weaker clock substitution if CLOCK_MONOTONIC is unavailable
   engine=assert(X4LAN_AUTHORITY_SHIP_ENGINE).new()
   for i=1,12 do frames[id(i)]='test-frame' end
   local net=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
   connection=net.open('127.0.0.1',cfg.native_gate_authority_fleet_port)
   wire=assert(X4LAN_AUTHORITY_FIXTURE_FLEET_WIRE).new(connection,
    cfg.slot=='p1' and 'SOURCE' or 'GUEST1',cfg.native_gate_authority_fleet_lease,frames,1)
  end
  local ffi=require('ffi')
  local samples, sampled={},{},{}
  for i=1,12 do
   local actor=assert(actors[i]); local ship=ffi.new('UniverseID',actor)
   local key=assert(engine.key(ship)); assert(key~='')
   local saved=assert(gate.saved_identity(tostring(ship):gsub('ULL$','')))
   assert(saved==cfg.native_gate_snapshot_fixture[i])
   if keys[i] then assert(keys[i]==key) else keys[i]=key end
   assert(engine.operational(ship) and engine.is_ship(ship))
   local sector=assert(engine.sector(ship));local sector_key=assert(engine.key(sector))
   if i>1 then assert(sector_key==sectors[1], 'fixtures do not share the test sector') end
   local sector_saved=assert(gate.saved_identity(tostring(sector):gsub('ULL$','')))
   assert(type(sector_saved)=='string' and sector_saved:match('^[0-9a-f]+$') and #sector_saved==16 and sector_saved~='0000000000000000')
   if sectors[i] then assert(sectors[i]==sector_key) else sectors[i]=sector_key end
   local timestamp=clock()
   local p=engine.pose(ship)
   assert(engine.operational(ship)); local after=assert(engine.sector(ship)); assert(engine.key(after)==sector_key)
   samples[id(i)]=p; sampled[id(i)]=timestamp
   if not enrolled then
    local hash=assert(X4LAN_SHA256.digest(sector_saved))
    assert(type(hash)=='string' and hash:match('^[0-9a-f]+$') and #hash==64)
    log(string.format('AUTHORITY_FLEET_ENROLL tick=%d id=%s sector=%s',tick,id(i),hash))
   end
  end
  enrolled=true
  local now=clock()
  local updates,sent=wire:step(cfg.slot=='p1' and samples or nil,now)
  if cfg.slot=='p1' then
   for _,row in ipairs(sent) do
    local p=assert(samples[row.fixture])
    log(string.format('AUTHORITY_FLEET_SOURCE tick=%d id=%s seq=%.0f time=%.9f x=%.17g y=%.17g z=%.17g',tick,row.fixture,row.sequence,sampled[row.fixture],p.x,p.y,p.z))
   end
  else
   for _,row in ipairs(updates) do
    log(string.format('AUTHORITY_FLEET_RECEIVE tick=%d id=%s request=%.0f seq=%.0f time=%.9f x=%.17g y=%.17g z=%.17g',tick,row.fixture,row.request,row.source_sequence,now,row.x,row.y,row.z))
   end
  end
 end)
 if not ok then
  disabled=true
  if connection then pcall(function() connection:close() end) end
  log('AUTHORITY_FLEET_ERROR tick='..tostring(tick))
 end
end
X4LAN_AUTHORITY_FIXTURE_FLEET_PROBE=M
return M
