-- Opt-in paused read-only wrapper. It registers no events and owns no queue.
-- The caller must fence the existing serialized job host while this is pending.
local M={}
local function finite(n)return type(n)=='number' and n==n and n>=0 and n<math.huge end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(type(o.core)=='table' and type(o.core.new)=='function')
 for _,k in ipairs({'guard','paused','game_time','docking','snapshot','issue'}) do assert(type(o[k])=='function',k..' required') end
 local baseline
 local function guard()
  if o.guard()~=true or o.paused()~=true then return false end
  local g=o.game_time();if not finite(g) then return false end
  baseline=baseline or g
  return g==baseline and o.paused()==true and o.guard()==true
 end
 local function undocked(actor)
  local a,b,c=o.docking(actor)
  return a==false and b==false and c==false
 end
 local options={};for k,v in pairs(o) do options[k]=v end
 options.guard=guard
 options.issue=function(screen,op,args)
  assert(screen=='X4AuthorityJobDescriptorProbe' and op=='Read')
  return o.issue('X4AuthorityPausedJobDescriptor',op,args)
 end
 options.snapshot=function(actor,sector)
  assert(guard() and undocked(actor) and guard())
  local sample=o.snapshot(actor,sector)
  assert(type(sample)=='table' and sample.game_before==baseline and sample.game_after==baseline)
  assert(guard() and undocked(actor) and guard())
  return sample
 end
 local inner=assert(o.core.new(options));local api={}
 function api:start() return inner:start() end
 function api:tick() return inner:tick() end
 function api:abort() return inner:abort() end
 function api:close() return inner:close() end
 function api:state() return inner:state() end
 function api:response(v)
  local ok,r=inner:response(v)
  if not ok then return ok,r end
  r.paused_checks_passed=true;r.continuous_pause_proven=false;r.docking_continuously_excluded=false
  return true,r
 end
 return api
end
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(type(c.core)=='table' and type(c.core.new)=='function' and type(c.guard)=='function' and type(c.expected_save_path)=='string'
  and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save')
 for _,k in ipairs({'AddUITriggeredEvent','GetCurRealTime','ConvertIDTo64Bit','ConvertStringToLuaID','GetComponentData'}) do assert(type(_G[k])=='function') end
 assert(type(X4LAN_RESOLVE_STRING)=='table' and type(X4LAN_RESOLVE_STRING.actor_u64)=='function' and type(X4LAN_RESOLVE_STRING.parse_hex)=='function')
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
 ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);UIPosRot GetObjectPositionInSector(UniverseID);
 double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local opts={};for k,v in pairs(c) do opts[k]=v end
 local function key(v)
  local n=X4LAN_RESOLVE_STRING.actor_u64(v);assert(n);local s=tostring(n):gsub('ULL$','');assert(s:match('^[1-9]%d*$'));return s
 end
 opts.actor_key=function(a)
  local original=X4LAN_RESOLVE_STRING.actor_u64(a);assert(original)
  local converted=X4LAN_RESOLVE_STRING.actor_u64(ConvertIDTo64Bit(a));assert(converted and original==converted)
  return key(converted)
 end
 opts.hex_key=function(v)local n=X4LAN_RESOLVE_STRING.parse_hex(v);assert(n);return key(n) end
 opts.clock=GetCurRealTime;opts.game_time=function()return tonumber(C.GetCurrentGameTime())end
 opts.paused=function()return C.IsGamePaused()end
 opts.guard=function()
  local p=C.GetSaveFolderPath()
  return c.guard()==true and p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==c.expected_save_path and C.IsPlayerValid()
 end
 opts.issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end
 opts.docking=function(actor)
  local id=key(actor);local ref=ConvertStringToLuaID(id);assert(ref~=nil and ref~=0 and key(ConvertIDTo64Bit(ref))==id)
  return GetComponentData(ref,'isdocked','isdocking','isinternallystored')
 end
 local function live(a,s)
  return C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and
   C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s
 end
 opts.snapshot=function(actor,sector_hex)
  local a=X4LAN_RESOLVE_STRING.actor_u64(actor);local s=X4LAN_RESOLVE_STRING.parse_hex(sector_hex)
  assert(a and s and live(a,s))
  local before=tonumber(C.GetCurrentGameTime());local p=C.GetObjectPositionInSector(a);local after=tonumber(C.GetCurrentGameTime())
  assert(live(a,s))
  return {sector_local=key(s),x=tonumber(p.x),y=tonumber(p.y),z=tonumber(p.z),game_before=before,game_after=after}
 end
 return M.new(opts)
end
X4LAN_AUTHORITY_PAUSED_JOB_DESCRIPTOR=M
return M
