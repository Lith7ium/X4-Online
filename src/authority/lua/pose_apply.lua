-- Opt-in, injected fixture experiment. No registration, FFI, scheduling or game
-- call occurs on load. This is a separate primitive mock stage, not a native
-- acceptance test (100 m / 0.1 m / 300 ticks), replication or production adapter.
-- Immediate and later samples do not prove a hold interval, atomicity, stable
-- object lifetime or safe physical clearance; a native harness must prove those.
local M = {}
local axes = {'x','y','z','yaw','pitch','roll'}
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function pose(p)
 assert(type(p)=='table','pose unavailable')
 local out={}
 for _,k in ipairs(axes) do
  assert(finite(p[k]),'invalid pose '..k)
  local limit=(k=='x' or k=='y' or k=='z') and 10000000 or 4*math.pi
  assert(math.abs(p[k]) <= limit, 'pose out of bounds')
  out[k]=p[k]
 end
 return out
end
local function same(a,b) return a~=nil and b~=nil and a==b end
local function distance(a,b)
 return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2)
end
local function angle(a,b) return math.abs((a-b+math.pi)%(2*math.pi)-math.pi) end
local function within(a,b)
 return distance(a,b)<=1 and angle(a.yaw,b.yaw)<=0.02 and
  angle(a.pitch,b.pitch)<=0.02 and angle(a.roll,b.roll)<=0.02
end

-- engine methods are plain functions. fixture and sector are local handles
-- enrolled from the same disposable save, not supplied by a network message.
-- identity callbacks and isolated() must be backed by a verified harness.
-- engine.pose returns sector-relative metres and angles in radians; set_pose
-- receives sector-relative metres and angles in degrees, as in the older X4
-- prototype. This convention has not been freshly validated in X4.
-- controlled_ship(), occupied_ship(), player_container(), and container()
-- return false for confirmed absence, nil for unknown, or a local handle.
-- The adapter must resolve the player's relevant containment to the ship;
-- a shallow/unknown parent chain is not an acceptable negative result.
function M.new(engine, identities, fixture, sector, expected)
 assert(type(engine)=='table' and type(identities)=='table' and type(expected)=='table','missing dependencies')
 assert(expected.enabled==true and expected.fixture_id=='test-only-fixture-1', 'experiment not explicitly enabled')
 assert(type(expected.sector_id)=='string' and #expected.sector_id>0 and #expected.sector_id<=256,'invalid sector identity')
 assert(fixture~=nil and sector~=nil, 'fixture and sector required')
 local sector_id=expected.sector_id
 local used=false
 local written_target
 local pinned_key,pinned_sector_key
 local function check()
  assert(engine.isolated()==true,'disposable profile not established')
  assert(engine.operational(fixture)==true and engine.is_ship(fixture)==true,'fixture unavailable')
  local key=engine.key(fixture); local sector_key=engine.key(sector)
  assert(type(key)=='string' and key~='' and type(sector_key)=='string' and sector_key~='', 'local key unavailable')
  if pinned_key then
   assert(key==pinned_key and sector_key==pinned_sector_key,'enrolled handle changed')
  else
   pinned_key,pinned_sector_key=key,sector_key
  end
  local function exclude_player(value,description)
   assert(value~=nil,description..' unknown')
   if value~=false then
    local own_key=engine.key(value)
    assert(type(own_key)=='string' and own_key~='' and own_key~=key,description..' unavailable or selected')
   end
  end
  exclude_player(engine.controlled_ship(),'controlled ship')
  exclude_player(engine.occupied_ship(),'occupied ship')
  exclude_player(engine.player_container(),'player container')
  assert(identities.ship(fixture)=='test-only-fixture-1' and identities.sector(sector)==sector_id,'fixture identity mismatch')
  assert(same(engine.key(engine.sector(fixture)),sector_key),'fixture sector mismatch')
  local docked,docking,stored=engine.dock_state(fixture)
  assert(docked==false and docking==false and stored==false,'fixture not confirmed free')
  assert(engine.container(fixture)==false,'fixture container unknown or present')
  return key,sector_key
 end
 local function sample()
  local key,sector_key=check()
  local value=pose(engine.pose(fixture))
  local key2,sector_key2=check()
  assert(key==key2 and sector_key==sector_key2,'fixture changed during sample')
  return value
 end
 local function attempt(target)
  if used then return nil,{attempted_write=false,error='experiment already attempted'} end
  used=true -- even a failed precondition requires a fresh harness
  local did_write=false
  local ok, result=pcall(function()
   local target_copy=pose(target)
   local before=sample()
   local displacement=distance(before,target_copy)
   -- At least 5 m so a no-op setter cannot pass the 1 m readback tolerance.
   assert(displacement>=5 and displacement<=50,'target must move fixture between 5 and 50 metres')
   check()
   did_write=true -- setter errors may follow a partial write
   local degrees={x=target_copy.x,y=target_copy.y,z=target_copy.z,
    yaw=target_copy.yaw*180/math.pi,pitch=target_copy.pitch*180/math.pi,roll=target_copy.roll*180/math.pi}
   engine.set_pose(fixture,sector,degrees)
   local immediate=sample()
   assert(within(immediate,target_copy),'immediate readback mismatch')
   -- Never expose the internal target table to the adapter or caller.
   written_target=pose(target_copy)
   return {before=before,target=pose(target_copy),immediate=immediate,immediate_matches=true}
  end)
  if not ok then return nil,{attempted_write=did_write,error=tostring(result)} end
  return result
 end
 local function observe(...)
  local argc=select('#',...)
  local ok,result=pcall(function()
   assert(argc==0,'observation takes no target')
   assert(written_target,'confirmed write required before observation')
   local current=sample()
   return {pose=current,matches=within(current,written_target)}
  end)
  if not ok then return nil,tostring(result) end
  return result
 end
 return {attempt=attempt,observe=observe}
end
return M
