-- Default-off local diagnostic. No event handlers or update callback are installed.
local M={}
local function token(s) return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function hex(s) return type(s)=='string' and #s<=18 and s:match('^0[xX][0-9a-fA-F]+$')~=nil end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.nonce) and finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,name in ipairs({'guard','issue','inspect'}) do assert(type(o[name])=='function') end
 local phase='idle';local busy=false;local failed=false;local game,started,last,result
 local api={}
 local function fault() failed=true;phase='failed';return false,'fault' end
 local function guarded()
  local t,g=o.guard()
  assert(finite(t) and t>=0 and finite(g) and g>=0 and (not last or t>=last))
  last=t;started=started or t;game=game or g;assert(game==g)
  return t
 end
 local function run(fn)
  if failed then return false,'fault' end
  if busy then return fault() end
  busy=true;local ok,value=pcall(fn);busy=false
  if not ok or failed then return fault() end
  return true,value
 end
 local function finish(reason)
  result={status='inconclusive',reason=reason,seat_free_proven=false,player_control_proven=false,
   same_actor_proven=false,coverage_proven=false};phase='done';return result
 end
 function api:start()
  return run(function()
   assert(phase=='idle');local t=guarded();assert(t-started<o.timeout)
   phase='waiting';assert(o.issue('X4AuthorityPositiveSeatSearch','Read',{epoch=o.epoch,request_id=o.nonce})==true)
   assert(not failed and guarded()-started<o.timeout)
  end)
 end
 function api:response(v)
  return run(function()
   assert(phase=='waiting' and guarded()-started<o.timeout and type(v)=='string' and #v<=256)
   local n,e,a,s,z=v:match('^([0-9a-f]+)|([0-9a-f]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|occupied$')
   assert(n==o.nonce and e==o.epoch and hex(a) and hex(s) and hex(z))
   local ok,status=pcall(o.inspect,a,s,z)
   assert(not failed and guarded()-started<o.timeout)
   if not ok or (status~='present' and status~='missing') then return finish('getter_or_context_unavailable') end
   if status=='missing' then return finish('assigned_pilot_not_observed') end
   phase='done';result={status='candidate_observed',seat_free_proven=false,player_control_proven=false,
    same_actor_proven=false,coverage_proven=false};return result
  end)
 end
 function api:inconclusive(v)
  return run(function()
   assert(phase=='waiting' and guarded()-started<o.timeout and v==o.nonce..'|'..o.epoch..'|inconclusive')
   return finish('search_inconclusive')
  end)
 end
 function api:refused() return fault() end
 function api:tick()
  return run(function()
   local t=guarded()
   if phase=='waiting' and t-started>=o.timeout then return finish('timeout') end
   assert(phase=='waiting' or phase=='done');return result
  end)
 end
 function api:state() return phase end
 return api
end
function M.new_x4(cfg)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 assert(type(cfg.expected_save_path)=='string' and cfg.expected_save_path:sub(1,1)=='/' and cfg.expected_save_path:sub(-11)=='/45841/save')
 for _,n in ipairs({'AddUITriggeredEvent','GetCurRealTime','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'}) do assert(type(_G[n])=='function') end
 assert(type(X4LAN_RESOLVE_STRING)=='table' and type(X4LAN_RESOLVE_STRING.parse_hex)=='function')
 local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local o={};for k,v in pairs(cfg) do o[k]=v end
 o.guard=function()
  local before=GetCurRealTime();local p=C.GetSaveFolderPath()
  assert(p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.expected_save_path)
  assert(C.IsPlayerValid() and C.IsGamePaused());local g=tonumber(C.GetCurrentGameTime());local t=GetCurRealTime()
  assert(finite(before) and finite(t) and t>=before and C.IsGamePaused());return t,g
 end
 o.issue=function(screen,op,args) return AddUITriggeredEvent(screen,op,args)~=false end
 o.inspect=function(ah,sh,zh)
  local a=X4LAN_RESOLVE_STRING.parse_hex(ah);local s=X4LAN_RESOLVE_STRING.parse_hex(sh);local z=X4LAN_RESOLVE_STRING.parse_hex(zh)
  local function context()
   return a and s and z and C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and
    C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.IsValidComponent(z) and C.IsComponentClass(z,'zone') and
    C.GetContextByClass(a,'sector',false)==s and C.GetContextByClass(a,'zone',false)==z
  end
  assert(context());local key=tostring(a):gsub('ULL$','');local id=ConvertStringToLuaID(key)
  assert(id~=nil and id~=false);local back=ConvertIDTo64Bit(id);assert(tostring(back):gsub('ULL$','')==key)
  local ok,pilot=pcall(GetComponentData,id,'assignedpilot');assert(ok)
  local status='missing'
  if pilot~=nil then
   local value=ConvertIDTo64Bit(pilot);assert(value~=nil and tostring(value):gsub('ULL$','')~='0')
   assert(C.IsValidComponent(ffi.new('UniverseID',value)));status='present'
  end
  assert(context());return status
 end
 return M.new(o)
end
X4LAN_AUTHORITY_POSITIVE_SEAT_SEARCH=M
return M
