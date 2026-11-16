-- Explicit private X4 binding; caller owns event registration and update loop.
local M={}
local SCREEN='X4AuthorityCensusReplica'
local names={'Initialized','Created','Inspection','Refused'}
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(c.exclusive_events==true and type(c.driver)=='table' and type(c.driver.new)=='function' and type(c.guard)=='function' and type(c.release_guard)=='function' and type(c.fault)=='function')
 assert(type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save')
 for _,k in ipairs({'RegisterEvent','AddUITriggeredEvent','GetCurRealTime','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'})do assert(type(_G[k])=='function')end
 assert(type(X4LAN_RESOLVE_STRING)=='table' and type(X4LAN_RESOLVE_STRING.parse_hex)=='function' and type(X4LAN_RESOLVE_STRING.actor_u64)=='function')
 assert(type(X4LAN_AUTHORITY_SHIP_ENGINE)=='table' and type(X4LAN_AUTHORITY_SHIP_ENGINE.new)=='function')
 local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
 ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);UniverseID GetContextByClass(UniverseID,const char*,bool);UIPosRot GetObjectPositionInSector(UniverseID);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local engine=X4LAN_AUTHORITY_SHIP_ENGINE.new();local state='new';local driver
 local function fail()if state~='failed' then state='failed';pcall(c.fault) end;return false end
 local function key(id)local n=X4LAN_RESOLVE_STRING.actor_u64(id);assert(n);local s=tostring(n):gsub('ULL$','');assert(s:match('^[1-9]%d*$'));return s end
 local function guard()
  local p=C.GetSaveFolderPath()
  if c.guard()~=true or p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=c.expected_save_path or not C.IsPlayerValid() or not C.IsGamePaused() then return false end
  local g=tonumber(C.GetCurrentGameTime());return finite(g) and g>=0,g
 end
 local function live(a,s)
  return C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s
 end
 local function lua_id(id)
  local ref=ConvertStringToLuaID(id);assert(ref~=nil and ref~=0)
  local kind=type(ref);assert(kind=='number' or kind=='cdata' or kind=='userdata')
  if kind~='userdata' then assert(key(ref)==id) end
  assert(key(ConvertIDTo64Bit(ref))==id);return ref
 end
 local function snapshot(actor,sector)
  local ok,g=guard();assert(ok);local a=X4LAN_RESOLVE_STRING.parse_hex(actor);local s=X4LAN_RESOLVE_STRING.parse_hex(sector);assert(a and s and live(a,s))
  local id=key(a);local ref=lua_id(id);local dock,docking,stored=GetComponentData(ref,'isdocked','isdocking','isinternallystored');assert(dock==false and docking==false and stored==false)
  local p=C.GetObjectPositionInSector(a);local again,game=guard();assert(again and game==g and live(a,s))
  local d2,q2,s2=GetComponentData(ref,'isdocked','isdocking','isinternallystored');assert(d2==false and q2==false and s2==false)
  return {actor_key=id,sector_key=key(s),x=tonumber(p.x),y=tonumber(p.y),z=tonumber(p.z)}
 end
 local function count(faction,macro)
  local ok,game=guard();assert(ok);local n=engine.fleet_count(faction);assert(finite(n) and n>=0 and n%1==0 and n<200000)
  local rows,cut=engine.fleet(faction,n+1);assert(not cut and type(rows)=='table' and #rows==n and engine.fleet_count(faction)==n)
  local seen,total={},0
  for _,ship in ipairs(rows)do
   local id=key(ship);assert(not seen[id] and C.IsValidComponent(ship));seen[id]=true
   if C.IsComponentOperational(ship) and C.IsComponentClass(ship,'ship') then
    local m=GetComponentData(lua_id(id),'macro');assert(type(m)=='string' and #m>0 and #m<=128 and m:match('^[%w_%-%.]+$'))
    if m==macro then total=total+1 end
   end
  end
  local good,after=guard();assert(good and after==game and engine.fleet_count(faction)==n);return total
 end
 local api={}
 function api:start(descriptor,witness)
  if state~='new' then return fail() end;state='registering'
  local ok=pcall(function()
   driver=assert(c.driver.new({enabled=true,epoch=c.epoch,attempt=c.attempt,nonce=c.nonce,timeout=c.timeout,
    clock=GetCurRealTime,guard=guard,release_guard=c.release_guard,count=count,snapshot=snapshot,
    issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end}))
   for _,n in ipairs(names)do local event=SCREEN..'.'..n
    assert(RegisterEvent(event,function(_,v)
     if state~='active' then fail();return end
     local good,accepted=pcall(driver.event,driver,event,v);if not good or accepted~=true then fail() end
    end)~=false and state=='registering')
   end
   state='active';assert(driver:start(descriptor,witness) and state=='active')
  end)
  if not ok or state=='failed' then return fail() end;return true
 end
 function api:tick()
  if state~='active' then return fail() end
  local ok,alive,phase=pcall(driver.tick,driver);if not ok or alive~=true or state~='active' then return fail() end
  return true,phase
 end
 function api:take_intent()
  if state~='active' then return fail() end
  local ok,accepted,intent=pcall(driver.take_intent,driver);if not ok or accepted~=true or state~='active' then return fail() end
  return true,intent
 end
 function api:state()return state=='active' and driver:state() or state end
 return api
end
return M
