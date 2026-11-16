-- Opt-in, local read only. No hooks, network, save, or setters on import.
-- The owner owns the event route, onUpdate, process fencing and output staging.
local M={}
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function finite(v)return type(v)=='number' and v==v and v>=0 and v<math.huge end
local function name(v)return type(v)=='string' and #v>=1 and #v<=128 and v:match('^[A-Za-z0-9_]+$')~=nil end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 assert(token(c.epoch) and token(c.incarnation) and token(c.nonce) and c.epoch~=c.incarnation and c.epoch~=c.nonce and c.incarnation~=c.nonce)
 assert(finite(c.timeout) and c.timeout>0 and c.timeout<=120)
 for _,k in ipairs({'clock','guard','issue','inspect','complete'})do assert(type(c[k])=='function',k)end
 local state,busy='idle',false;local last,deadline,pending=nil,nil,nil;local count=0;local api={}
 local by_macro,by_key={},{};local sectors=0
 local function fail(reason)state='failed';pending=nil;deadline=nil;return false,reason end
 local function call(fn,...)
  local before=state;local ok,a,b=pcall(fn,...)
  if not ok or state~=before then return false end
  return true,a,b
 end
 local function check()
  if state=='failed' or state=='closed' then return false end
  local ok,t=call(c.clock)
  if not ok or not finite(t) or (last and t<last) or (deadline and t>=deadline)then return false end
  last=t;local a,g=call(c.guard,c.incarnation);if not a or g~=true then return false end
  local b,u=call(c.clock)
  if not b or not finite(u) or u<t or (deadline and u>=deadline)then return false end
  last=u;return true
 end
 function api:begin()
  if busy or state~='idle' or count>=4294967295 then return fail('begin')end
  busy=true;local ok=pcall(function()
   assert(check());count=count+1;pending={id=c.nonce..'-'..tostring(count),sequence=count}
   state='pending';deadline=last+c.timeout;assert(check())
   assert(c.issue('X4AuthorityPlayerSectorInterest','Read',{request_id=pending.id,epoch=c.epoch,incarnation=c.incarnation})==true)
   assert(state=='pending' and check())
  end);busy=false;if not ok then return fail('dispatch')end;return true
 end
 function api:event(v)
  if busy or state~='pending' then return fail('event')end
  busy=true;local ok=pcall(function()
   assert(check() and type(v)=='string' and #v<=512)
   local id,epoch,inc,sector,macro=v:match('^([0-9a-f]+%-%d+)|([0-9a-f]+)|([0-9a-f]+)|ok|(0[xX][0-9a-fA-F]+)|([A-Za-z0-9_]+)$')
   assert(id==pending.id and epoch==c.epoch and inc==c.incarnation and name(macro))
   local inspected,key=call(c.inspect,sector,macro);assert(inspected and type(key)=='string' and key:match('^[1-9]%d*$') and #key<=20 and check())
   assert((not by_macro[macro] or by_macro[macro]==key) and (not by_key[key] or by_key[key]==macro))
   if not by_macro[macro] then assert(sectors<4096)end
   local out={epoch=c.epoch,incarnation=c.incarnation,sequence=pending.sequence,sector_macro=macro}
   state='delivering';local sent,accepted=call(c.complete,out)
   assert(sent and accepted==true and getmetatable(out)==nil and out.epoch==c.epoch and out.incarnation==c.incarnation and
    out.sequence==pending.sequence and out.sector_macro==macro and check())
   for k in pairs(out)do assert(k=='epoch' or k=='incarnation' or k=='sequence' or k=='sector_macro')end
   local again,after=call(c.inspect,sector,macro);assert(again and after==key and check())
   if not by_macro[macro] then sectors=sectors+1;by_macro[macro]=key;by_key[key]=macro end
   pending=nil;deadline=nil;state='idle'
  end);busy=false;if not ok then return fail('response')end;return true
 end
 function api:tick()if busy or not check()then return fail('guard')end;return true end
 function api:expected_request()return state=='pending' and pending.id or nil end
 function api:state()return state end
 function api:close()if busy then return fail('close')end;state='closed';pending=nil;deadline=nil;return true end
 return api
end
function M.new_x4(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 assert(type(c.guard)=='function' and type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save')
 assert(type(c.resolve)=='table' and c.resolve==X4LAN_RESOLVE_STRING and type(c.resolve.parse_hex)=='function' and type(c.resolve.actor_u64)=='function')
 for _,k in ipairs({'GetCurRealTime','AddUITriggeredEvent','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'})do assert(type(_G[k])=='function')end
 local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID')then ffi.cdef('typedef uint64_t UniverseID;')end
 ffi.cdef[[bool IsPlayerValid(void);bool IsValidComponent(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetPlayerContainerID(void);UniverseID GetContextByClass(UniverseID,const char*,bool);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local parse,u64=c.resolve.parse_hex,c.resolve.actor_u64
 local external,path,clock,issue,data,to_lua,to64=c.guard,c.expected_save_path,GetCurRealTime,AddUITriggeredEvent,GetComponentData,ConvertStringToLuaID,ConvertIDTo64Bit
 local function environment()
  local p=C.GetSaveFolderPath()
  return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==path and C.IsPlayerValid()
 end
 c.clock=clock;c.guard=function(inc)return environment() and external(inc)==true and environment()end
 c.issue=function(screen,op,args)return issue(screen,op,args)~=false end
 c.inspect=function(text,macro)
  local sector=parse(text);if not sector then return nil end
  local key=tostring(sector):gsub('ULL$','');local ref=to_lua(key);local typ=type(ref)
  if typ=='number' or typ=='cdata' then if u64(ref)~=sector then return nil end elseif typ~='userdata' then return nil end
  if u64(to64(ref))~=sector then return nil end
  local function live()
   local p=C.GetPlayerContainerID()
   return p~=0 and C.IsValidComponent(p) and C.IsValidComponent(sector) and C.IsComponentClass(sector,'sector') and
    C.GetContextByClass(p,'sector',true)==sector
  end
  if not c.guard(c.incarnation) or not live() or data(ref,'macro')~=macro or not c.guard(c.incarnation) or not live() then return nil end
  return key
 end
 return M.new(c)
end
X4LAN_PLAYER_SECTOR_INTEREST=M
return M
