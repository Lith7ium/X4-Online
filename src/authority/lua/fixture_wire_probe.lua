-- Disposable Linux diagnostic: read one enrolled fixture and exchange its pose.
-- No game writes. All local configuration and endpoints are supplied by runner.
local M={}
local wire, connection, engine, disabled, pinned_sector
function M.sample(cfg,tick,actors,log)
 if cfg.native_gate_authority_wire ~= true or disabled or tick < 30 then return end
 local ok = pcall(function()
  if not wire then
   assert(cfg.test_profile=='45841' and (cfg.slot=='p1' or cfg.slot=='p2'))
   assert(type(cfg.native_gate_authority_wire_port)=='number' and cfg.native_gate_authority_wire_port%1==0
    and cfg.native_gate_authority_wire_port>=1 and cfg.native_gate_authority_wire_port<=65535)
   local role=cfg.slot=='p1' and 'SOURCE' or 'GUEST'
   local net=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
   connection=net.open('127.0.0.1',cfg.native_gate_authority_wire_port)
   wire=assert(X4LAN_AUTHORITY_FIXTURE_WIRE).new(connection,role,cfg.native_gate_authority_wire_lease,'test-only-fixture-1')
   if role=='SOURCE' then engine=assert(X4LAN_AUTHORITY_SHIP_ENGINE).new() end
  end
  local position
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
  local before=wire.sent
  local received=wire:step(position)
  if cfg.slot=='p1' and wire.sent>before then
   log(string.format('AUTHORITY_WIRE_SOURCE tick=%d seq=%.0f x=%.17g y=%.17g z=%.17g',tick,wire.sent,position.x,position.y,position.z))
  elseif received then
   log(string.format('AUTHORITY_WIRE_RECEIVE tick=%d request=%.0f seq=%.0f x=%.17g y=%.17g z=%.17g',tick,received.request,received.source_sequence,received.x,received.y,received.z))
  end
 end)
 if not ok then
  disabled=true
  if connection then pcall(function() connection:close() end) end
  -- Never include Lua error messages, raw handles or role leases in logs.
  log('AUTHORITY_WIRE_ERROR tick='..tostring(tick))
 end
end
X4LAN_AUTHORITY_FIXTURE_WIRE_PROBE=M
return M
