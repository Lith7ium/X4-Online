-- Opt-in, one-request, read-only local witness check. Import owns no events.
local M={}
local SCREEN='X4AuthoritySectorWitnessRuntime'
local function token(s)return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function integer(n)return type(n)=='number' and n==n and n>=1 and n<=9007199254740991 and n%1==0 end
local function finite(n)return type(n)=='number' and n==n and n>=0 and n<math.huge end
local function name(s)return type(s)=='string' and #s>=1 and #s<=128 and s:match('^[%w_%-%.]+$')~=nil and s~='nil' and s~='null' end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.request_id) and integer(o.index) and name(o.macro) and finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,k in ipairs({'clock','guard','paused','game_time','issue','verify'}) do assert(type(o[k])=='function',k..' required') end
 local state='idle';local busy=false;local generation={};local last,deadline,game0
 local function fail(s)state='failed';generation={};return false,s end
 local function call(fn,...)
  if busy then return fail('reentrant') end
  local g,p=generation,state;busy=true;local ok,a=pcall(fn,...);busy=false
  if g~=generation or p~=state then return fail('state_changed') end
  if not ok then return fail('callback') end
  return true,a
 end
 local function check()
  if state=='failed' or state=='closed' or state=='done' then return false end
  local ok,t=call(o.clock);if not ok then return false end
  if not finite(t) or (last and t<last) or (deadline and t>=deadline) then return fail('deadline') end;last=t
  local a,guard=call(o.guard);local b,paused=call(o.paused);local c,game=call(o.game_time)
  if not a or not b or not c or guard~=true or paused~=true or not finite(game) or (game0 and game~=game0) then return fail('context') end
  game0=game0 or game
  local d,t2=call(o.clock);if not d or not finite(t2) or t2<last or (deadline and t2>=deadline) then return fail('deadline') end;last=t2
  return true
 end
 local api={}
 function api:start()
  if state~='idle' or not check() then return fail('start') end
  state='waiting';generation={};deadline=last+o.timeout
  if not finite(deadline) or not check() then return fail('deadline') end
  local ok,sent=call(o.issue,SCREEN,'Read',{epoch=o.epoch,index=o.index,request_id=o.request_id,macro=o.macro})
  if not ok or sent~=true or not check() then return fail('dispatch') end
  return true
 end
 function api:response(value)
  if state~='waiting' or not check() then return fail('unexpected') end
  if type(value)~='string' or #value>768 then return fail('response') end
  local rid,epoch,index,actor,sector,macro=value:match('^([0-9a-f]+)|([0-9a-f]+)|([0-9]+)|ok|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([%w_%-%.]+)$')
  if rid~=o.request_id or epoch~=o.epoch or index~=string.format('%.0f',o.index) or macro~=o.macro then return fail('unavailable_or_mismatch') end
  local ok,match=call(o.verify,actor,sector)
  if not ok or match~=true or not check() then return fail('local_context') end
  local again,still=call(o.verify,actor,sector)
  if not again or still~=true or not check() then return fail('local_context') end
  state='done';deadline=nil
  return true,{epoch=o.epoch,index=o.index,sector_macro=o.macro,game_time=game0,
   local_witness_match=true,cross_process_identity_proven=false,atomic_snapshot_proven=false,continuous_pause_proven=false}
 end
 function api:tick() if state=='waiting' then return check() end;return fail('not_waiting') end
 function api:close()state='closed';generation={};deadline=nil;return true end
 function api:abort()return fail('external_fence')end
 function api:state()return state end
 return api
end
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(type(c.guard)=='function' and type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save')
 for _,k in ipairs({'GetCurRealTime','AddUITriggeredEvent','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'}) do assert(type(_G[k])=='function') end
 assert(type(X4LAN_RESOLVE_STRING)=='table' and type(X4LAN_RESOLVE_STRING.parse_hex)=='function' and type(X4LAN_RESOLVE_STRING.actor_u64)=='function')
 local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);UniverseID GetContextByClass(UniverseID,const char*,bool);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local o={};for k,v in pairs(c) do o[k]=v end
 local function key(n)n=X4LAN_RESOLVE_STRING.actor_u64(n);assert(n);local s=tostring(n):gsub('ULL$','');assert(s:match('^[1-9]%d*$'));return s end
 o.clock=GetCurRealTime;o.game_time=function()return tonumber(C.GetCurrentGameTime())end;o.paused=function()return C.IsGamePaused()end
 o.guard=function()
  local p=C.GetSaveFolderPath();return c.guard()==true and p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==c.expected_save_path and C.IsPlayerValid()
 end
 o.issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end
 o.verify=function(actor_hex,sector_hex)
  local a=X4LAN_RESOLVE_STRING.parse_hex(actor_hex);local s=X4LAN_RESOLVE_STRING.parse_hex(sector_hex)
  assert(a and s and C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s)
  local id=key(a);local ref=ConvertStringToLuaID(id);assert(ref~=nil and ref~=0 and key(ConvertIDTo64Bit(ref))==id)
  local docked,docking,stored=GetComponentData(ref,'isdocked','isdocking','isinternallystored')
  assert(docked==false and docking==false and stored==false)
  return C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s
 end
 return M.new(o)
end
return M
