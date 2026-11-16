-- Explicitly installed X4 adapter; it registers events only on start and never
-- creates an onUpdate handler or socket. Callback values contain no handles.
local M={}
local names={'X4AuthorityShipCreateReceiver.Initialized','X4AuthorityShipCreateReceiver.Created',
 'X4AuthorityShipCreateReceiver.Refused','X4AuthorityPairCreateInspect.Result','X4AuthorityPairCreateInspect.Refused'}
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(c.exclusive_events==true and type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save')
 assert(type(c.driver)=='table' and type(c.driver.new)=='function' and type(c.emit_descriptor)=='function' and type(c.inspect_complete)=='function' and type(c.fault)=='function')
 assert(type(X4LAN_RESOLVE_STRING)=='table' and type(X4LAN_RESOLVE_STRING.parse_hex)=='function' and type(X4LAN_RESOLVE_STRING.actor_u64)=='function')
 assert(type(X4LAN_AUTHORITY_SHIP_ENGINE)=='table' and type(X4LAN_AUTHORITY_SHIP_ENGINE.new)=='function')
 for _,k in ipairs({'RegisterEvent','AddUITriggeredEvent','GetCurRealTime','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'}) do assert(type(_G[k])=='function') end
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
 ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);UIPosRot GetObjectPositionInSector(UniverseID);
 double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local engine=X4LAN_AUTHORITY_SHIP_ENGINE.new();local state='new';local driver
 local function fail()if state~='failed' then state='failed';pcall(c.fault) end;return false end
 local function guard()
  local p=C.GetSaveFolderPath()
  if p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=c.expected_save_path or not C.IsPlayerValid() or not C.IsGamePaused() then return false end
  local game=tonumber(C.GetCurrentGameTime());if not finite(game) or game<0 then return false end
  return true,game
 end
 local function key(v)
  v=X4LAN_RESOLVE_STRING.actor_u64(v);assert(v,'invalid local ID')
  local s=tostring(v):gsub('ULL$','');assert(s:match('^[1-9]%d*$'));return s
 end
 local function live(a,s)
  return C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and
   C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s
 end
 local function snapshot(actor_hex,sector_hex)
  local ok,game=guard();assert(ok)
  local a=X4LAN_RESOLVE_STRING.parse_hex(actor_hex);local s=X4LAN_RESOLVE_STRING.parse_hex(sector_hex)
  assert(a and s and live(a,s));local p=C.GetObjectPositionInSector(a)
  local x,y,z=tonumber(p.x),tonumber(p.y),tonumber(p.z)
  assert(finite(x) and finite(y) and finite(z));local valid,after=guard();assert(valid and after==game and live(a,s))
  return {x=x,y=y,z=z,actor_key=key(a),sector_key=key(s)}
 end
 local function count()
  local ok,game=guard();assert(ok)
  local n=engine.fleet_count('argon');assert(finite(n) and n%1==0 and n>=0 and n<200000)
  local rows,cut=engine.fleet('argon',n+1);assert(not cut and type(rows)=='table' and #rows==n and engine.fleet_count('argon')==n)
  local seen,total={},0
  for _,ship in ipairs(rows) do
   local id=key(ship);assert(not seen[id] and C.IsValidComponent(ship));seen[id]=true
   if C.IsComponentOperational(ship) and C.IsComponentClass(ship,'ship') then
    local ref=ConvertStringToLuaID(id);assert(ref~=nil and ref~=0)
    local kind=type(ref);assert(kind=='number' or kind=='cdata' or kind=='userdata')
    if kind~='userdata' then assert(key(ref)==id) end
    assert(key(ConvertIDTo64Bit(ref))==id)
    local macro=GetComponentData(ref,'macro');assert(type(macro)=='string' and macro:match('^[%w_%-%.]+$'))
    if macro=='ship_arg_s_fighter_01_a_macro' then total=total+1 end
   end
  end
  local valid,after=guard();assert(valid and after==game and engine.fleet_count('argon')==n);return total
 end
 local api={}
 function api:start()
  if state~='new' then return fail() end
  state='registering'
  local ok=pcall(function()
   driver=assert(c.driver.new({enabled=true,role=c.role,epoch=c.epoch,attempt=c.attempt,nonce=c.nonce,sector=c.sector,timeout=c.timeout,
    clock=GetCurRealTime,guard=guard,count=count,snapshot=snapshot,emit_descriptor=c.emit_descriptor,inspect_complete=c.inspect_complete,
    issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end}))
   for _,name in ipairs(names) do
    assert(RegisterEvent(name,function(_,value)
     if state~='active' then fail();return end
     local good,accepted=pcall(driver.event,driver,name,value)
     if not good or accepted~=true then fail() end
    end)~=false and state=='registering')
   end
   state='active';assert(driver:start() and state=='active')
  end)
  if not ok or state=='failed' then return fail() end
  return true
 end
 function api:update()
  if state~='active' then return fail() end
  local ok,alive=pcall(driver.tick,driver);if not ok or alive~=true then return fail() end
  return true,driver:state()
 end
 function api:accept_descriptor(v)
  if state~='active' then return fail() end
  local ok,accepted=pcall(driver.accept_descriptor,driver,v);if not ok or accepted~=true then return fail() end
  return true
 end
 function api:confirm_ack(v)
  if state~='active' then return fail() end
  local ok,accepted=pcall(driver.confirm_ack,driver,v);if not ok or accepted~=true then return fail() end
  return true
 end
 function api:state()return state=='active' and driver:state() or state end
 return api
end
return M
