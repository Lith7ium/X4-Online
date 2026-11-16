-- Opt-in local FFI readback for a separately correlated MD Inspect response.
-- Import installs no handler, timer, UI hook or game call.
local M={}
local MAX=9007199254740991
local function finite(v)return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge end
local function integer(v)return finite(v) and v>=1 and v<=MAX and v%1==0 end
local function name(v)return type(v)=='string' and #v>=1 and #v<=128 and v:match('^[%w_%-%.]+$')~=nil end

-- `md_inspected` is an explicit assertion by the exclusive caller that the
-- exact descriptor/index and both returned local IDs came from its current,
-- separately correlated MD Inspect response. This module cannot read MD tables.
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(o.md_inspected==true and o.frame_confirmed==true, 'correlated MD inspect and frame assertion required')
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=30)
 assert(finite(o.position_tolerance) and o.position_tolerance>=0 and o.position_tolerance<=2)
 local timeout,tolerance=o.timeout,o.position_tolerance
 local callbacks={}
 for _,k in ipairs({'clock','guard','parse','key','reference','same','live','properties','position'}) do
  assert(type(o[k])=='function',k..' required');callbacks[k]=o[k]
 end
 local phase,busy='ready',false;local last,deadline
 local api={}
 local function fail(reason)phase='failed';return nil,false,reason end
 local function call(fn,...)
  if busy then return fail('reentrant') end
  local old=phase;busy=true;local ok,a,b,c,d,e=pcall(fn,...);busy=false
  if not ok or old~=phase then return fail('callback') end
  return a,b,c,d,e
 end
 local function time()
  local t=call(callbacks.clock)
  if not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return nil end
  last=t;return t
 end
 local function guard(expected)
  if not time() then return nil end
  local ok,game=call(callbacks.guard)
  if ok~=true or not finite(game) or game<0 or (expected and game~=expected) or not time() then return nil end
  return game
 end
 local function live(a,s)
  return call(callbacks.live,a,s)==true
 end
 function api:inspect(actor_hex,sector_hex,index,d)
  if phase~='ready' or busy then return fail('not_ready') end
  if not integer(index) or type(d)~='table' or getmetatable(d)~=nil or d.index~=index or
   not name(d.macro) or not name(d.owner) or not name(d.sector) or
   not finite(d.x) or not finite(d.y) or not finite(d.z) then return fail('invalid_descriptor') end
  -- Immutable local copy: injected guards/FFI must not alter expected values.
  local expected={index=index,macro=d.macro,owner=d.owner,sector=d.sector,x=d.x,y=d.y,z=d.z}
  local start=time();if not start then return fail('clock') end;deadline=start+timeout
  if not finite(deadline) then return fail('deadline') end
  local game=guard();if not game then return fail('guard') end
  local actor=call(callbacks.parse,actor_hex);local sector=call(callbacks.parse,sector_hex)
  if not actor or not sector then return fail('invalid_reference') end
  local actor_key=call(callbacks.key,actor);local sector_key=call(callbacks.key,sector)
  if type(actor_key)~='string' or not actor_key:match('^[1-9]%d*$') or
    type(sector_key)~='string' or not sector_key:match('^[1-9]%d*$') then return fail('invalid_key') end
  local actor_ref=call(callbacks.reference,actor_key);local sector_ref=call(callbacks.reference,sector_key)
  if not actor_ref or not sector_ref or call(callbacks.same,actor_ref,actor)~=true or call(callbacks.same,sector_ref,sector)~=true then return fail('reference_roundtrip') end
  if not live(actor,sector) or not guard(game) then return fail('actor_unavailable') end
  local macro,owner,docked,docking,stored=call(callbacks.properties,actor_ref)
  if macro~=expected.macro or owner~=expected.owner or docked~=false or docking~=false or stored~=false then return fail('properties') end
  local x,y,z=call(callbacks.position,actor)
  if not finite(x) or not finite(y) or not finite(z) or math.abs(x-expected.x)>tolerance or
    math.abs(y-expected.y)>tolerance or math.abs(z-expected.z)>tolerance then return fail('position') end
  if not live(actor,sector) or not guard(game) then return fail('binding_changed') end
  local macro2,owner2,docked2,docking2,stored2=call(callbacks.properties,actor_ref)
  if macro2~=expected.macro or owner2~=expected.owner or docked2~=false or docking2~=false or stored2~=false or not guard(game) then return fail('properties_changed') end
  if getmetatable(d)~=nil or d.index~=expected.index or d.macro~=expected.macro or d.owner~=expected.owner or
    d.sector~=expected.sector or d.x~=expected.x or d.y~=expected.y or d.z~=expected.z then return fail('descriptor_changed') end
  deadline=nil;return actor_key,true
 end
 function api:state()return phase end
 return api
end

function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(c.md_inspected==true and c.frame_confirmed==true and type(c.guard)=='function')
 assert(type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save')
 local resolve=assert(c.resolve);assert(type(resolve.parse_hex)=='function' and type(resolve.actor_u64)=='function')
 for _,k in ipairs({'GetCurRealTime','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'}) do assert(type(_G[k])=='function',k..' unavailable') end
 local expected_path,external_guard=c.expected_save_path,c.guard
 local parse,actor_u64=resolve.parse_hex,resolve.actor_u64
 local clock,component_data,to_lua_id,to64=GetCurRealTime,GetComponentData,ConvertStringToLuaID,ConvertIDTo64Bit
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
 ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);UIPosRot GetObjectPositionInSector(UniverseID);
 double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C
 local function u64(v)return actor_u64(v)end
 local function key(v)local n=u64(v);if not n then return nil end;return tostring(n):gsub('ULL$','')end
 local function guard()
  local path=C.GetSaveFolderPath()
  if path==nil or path==ffi.NULL or ffi.string(path):gsub('\\','/'):gsub('/+$','')~=expected_path or
    not C.IsPlayerValid() or not C.IsGamePaused() or external_guard()~=true then return false end
  local game=tonumber(C.GetCurrentGameTime());return finite(game),game
 end
 return M.new({enabled=true,md_inspected=true,frame_confirmed=true,timeout=c.timeout,
  position_tolerance=c.position_tolerance,clock=clock,guard=guard,
  parse=parse,key=key,reference=function(v)return to_lua_id(v)end,
  same=function(ref,value)
   local kind=type(ref)
   if kind=='number' then if not integer(ref) then return false end
   elseif kind~='cdata' and kind~='userdata' then return false end
   local converted=u64(to64(ref));return converted~=nil and converted==value
  end,
  live=function(a,s)return C.IsPlayerValid() and C.IsGamePaused() and C.IsValidComponent(a) and
   C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and C.IsValidComponent(s) and
   C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s end,
  properties=function(ref)return component_data(ref,'macro','owner','isdocked','isdocking','isinternallystored')end,
  position=function(a)local p=C.GetObjectPositionInSector(a);return tonumber(p.x),tonumber(p.y),tonumber(p.z)end})
end
return M
