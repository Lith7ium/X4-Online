-- Default-off integration. Existing private load owner alone calls the tick.
local M={}
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<math.huge end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,n in ipairs({'guard','make','log'}) do assert(type(o[n])=='function') end
 local phase='new';local busy=false;local failed=false;local start,last,game,actor,sector,probe,outcome,reason
 local reasons={timeout=true,search_inconclusive=true,getter_or_context_unavailable=true,assigned_pilot_not_observed=true}
 local function fail() if not failed then failed=true;phase='failed';pcall(o.log,'ERROR FAULT') end;return false end
 local function guarded()
  local t,g,a,s=o.guard();assert(finite(t) and finite(g) and t>=0 and g>=0 and type(a)=='string' and a~='' and type(s)=='string' and s~='')
  start=start or t;assert((not last or t>=last) and t-start<o.timeout);last=t
  if game then assert(game==g and actor==a and sector==s) else game,actor,sector=g,a,s end
 end
 local function action(fn)
  if failed or busy then return fail() end;busy=true
  local ok=pcall(function()guarded();fn();assert(not failed);guarded()end);busy=false
  if not ok or failed then return fail() end;return true
 end
 local function record(value)
  assert(type(value)=='table' and (value.status=='candidate_observed' or value.status=='inconclusive') and
   value.seat_free_proven==false and value.player_control_proven==false and value.same_actor_proven==false and value.coverage_proven==false)
  if value.status=='inconclusive' then assert(reasons[value.reason]);reason=value.reason
  else assert(value.reason==nil);reason=nil end
  outcome=value.status;phase='ready_to_report'
 end
 local api={}
 function api:tick()
  return action(function()
   if phase=='new' then
    probe=o.make();assert(probe);phase='waiting';assert(probe:start());assert(not failed);o.log('START')
   elseif phase=='waiting' then
    local ok,r=probe:tick();assert(ok and not failed)
    if probe:state()=='done' then record(r) end
   elseif phase=='ready_to_report' then
    guarded();phase='done';o.log(outcome=='candidate_observed' and 'CANDIDATE' or 'INCONCLUSIVE|'..reason);o.log('DONE')
   else assert(phase=='done') end
  end)
 end
 function api:response(v)
  return action(function()assert(phase=='waiting' and probe);local ok,r=probe:response(v);assert(ok and not failed);record(r)end)
 end
 function api:inconclusive(v)
  return action(function()assert(phase=='waiting' and probe);local ok,r=probe:inconclusive(v);assert(ok and not failed);record(r)end)
 end
 function api:refused() return fail() end
 function api:state() return phase end
 return api
end
X4LAN_AUTHORITY_POSITIVE_SEAT_LIVE_OWNER=M
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_positive_seat_live~=true then return M end
local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
local C=ffi.C
local function norm(x)return tostring(x):gsub('ULL$','')end
local function guard()
 local before=GetCurRealTime();local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 assert(C.IsPlayerValid() and C.IsGamePaused())
 local a,s,_,initial=X4LAN_SECTOR_READ_EXPORT();local g=tonumber(C.GetCurrentGameTime())
 assert(g==initial and C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and
  C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s)
 local after=GetCurRealTime();assert(finite(before) and finite(after) and after>=before and C.IsGamePaused())
 return after,g,norm(a),norm(s)
end
local app=M.new{enabled=true,timeout=cfg.authority_positive_seat_timeout,guard=guard,
 make=function()return X4LAN_AUTHORITY_POSITIVE_SEAT_SEARCH.new_x4{enabled=true,epoch=cfg.authority_sector_epoch,
  nonce=cfg.authority_positive_seat_nonce,timeout=math.min(10,cfg.authority_positive_seat_timeout/2),expected_save_path=cfg.authority_read_save_path}end,
 log=function(s)DebugError('[X4LAN] AUTH_POSITIVE_SEAT_LIVE '..s)end}
RegisterEvent('X4AuthorityPositiveSeatSearch.Result',function(_,v) app:response(v) end)
RegisterEvent('X4AuthorityPositiveSeatSearch.Inconclusive',function(_,v) app:inconclusive(v) end)
RegisterEvent('X4AuthorityPositiveSeatSearch.Refused',function() app:refused() end)
function X4LAN_POSITIVE_SEAT_LIVE_TICK() if not app:tick() then error('positive seat search failed') end end
return M
