-- Opt-in local read of a saved-registry actor. No hooks, sockets or writes.
-- Actor/sector references never leave this X4 process.
local M={}
local MAX=9007199254740991
local function integer(v)return type(v)=='number' and v==v and v>=1 and v<=MAX and v%1==0 end
local function finite(v)return type(v)=='number' and v==v and v>=0 and v<math.huge end
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function name(v)return type(v)=='string' and #v>=1 and #v<=128 and v:match('^[%w_%-]+$')~=nil end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 assert(token(c.epoch) and token(c.nonce) and integer(c.baseline) and finite(c.timeout) and c.timeout>0 and c.timeout<=120)
 for _,k in ipairs({'clock','guard','baseline_guard','issue','parse','inspect','complete'})do assert(type(c[k])=='function',k)end
 local state,busy='idle',false;local last,deadline,pending,count=nil,nil,nil,0;local api={}
 local function fail(reason)state='failed';pending=nil;deadline=nil;return false,reason end
 local function check()
  if state=='failed' or state=='closed' then return false end
  local before=state;local ok,t=pcall(c.clock)
  if not ok or state~=before or not finite(t) or (last and t<last) or (deadline and t>=deadline) then return false end
  last=t;local a,good=pcall(c.guard)
  if not a or good~=true or state~=before then return false end
  local b,baseline=pcall(c.baseline_guard,c.epoch,c.baseline)
  if not b or baseline~=true or state~=before then return false end
  local q,again=pcall(c.guard)
  if not q or again~=true or state~=before then return false end
  local z,u=pcall(c.clock)
  if not z or state~=before or not finite(u) or u<t or (deadline and u>=deadline) then return false end
  last=u;return true
 end
 function api:begin(index)
  if busy or state~='idle' or not integer(index) or index>c.baseline or count>=4294967295 then return fail('begin')end
  busy=true;local ok=pcall(function()
   assert(check());count=count+1
   pending={index=index,id=c.nonce:sub(1,16)..string.format('%016x',count)}
   deadline=last+c.timeout;state='pending';assert(check())
   assert(c.issue('X4AuthorityJobDescriptorProbe','Read',{epoch=c.epoch,index=index,request_id=pending.id})==true)
   assert(state=='pending' and check())
  end);busy=false;if not ok then return fail('dispatch')end;return true
 end
 function api:event(value)
  if busy or state~='pending' then return fail('event')end
  busy=true;local ok=pcall(function()
   assert(check() and type(value)=='string' and #value<=768)
   local id,epoch,index,status,actor,macro,owner,sector,sector_macro=value:match('^([0-9a-f]+)|([0-9a-f]+)|([0-9]+)|([a-z]+)|(0[xX][0-9a-fA-F]+)|([^|]+)|([^|]+)|(0[xX][0-9a-fA-F]+)|([^|]+)$')
   assert(id==pending.id and epoch==c.epoch and index==string.format('%.0f',pending.index) and status=='ok')
   assert(name(macro) and name(owner) and name(sector_macro))
   local a,s=c.parse(actor),c.parse(sector);assert(a~=nil and s~=nil and check())
   assert(c.inspect(a,s,sector_macro)==true and check())
   local i=pending.index;state='delivering';assert(c.complete(i,a,sector_macro)==true)
   assert(state=='delivering' and check() and c.inspect(a,s,sector_macro)==true and check())
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
 assert(type(c.guard)=='function' and type(c.baseline_guard)=='function' and type(c.expected_save_path)=='string')
 assert(type(c.resolve)=='table' and c.resolve==X4LAN_RESOLVE_STRING and type(c.resolve.parse_hex)=='function' and type(c.resolve.actor_u64)=='function')
 for _,k in ipairs({'GetCurRealTime','AddUITriggeredEvent','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'})do assert(type(_G[k])=='function')end
 local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID')then ffi.cdef('typedef uint64_t UniverseID;')end
 ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);
 bool IsComponentClass(UniverseID,const char*);UniverseID GetContextByClass(UniverseID,const char*,bool);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local parse,u64=c.resolve.parse_hex,c.resolve.actor_u64
 local clock,trigger,data,to_lua,to64=GetCurRealTime,AddUITriggeredEvent,GetComponentData,ConvertStringToLuaID,ConvertIDTo64Bit
 local external,path=c.guard,c.expected_save_path
 local function environment()
  local p=C.GetSaveFolderPath()
  return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==path and C.IsPlayerValid() and not C.IsGamePaused()
 end
 c.guard=function()return environment() and external()==true and environment()end
 c.clock=clock;c.parse=parse
 c.issue=function(screen,op,args)return trigger(screen,op,args)~=false end
 local function ref(id)
  local key=tostring(id):gsub('ULL$','');local v=to_lua(key);local kind=type(v)
  if kind=='number' or kind=='cdata' then local direct=u64(v);if not direct or direct~=id then return nil end
  elseif kind~='userdata' then return nil end
  local converted=u64(to64(v));if not converted or converted~=id then return nil end
  return v
 end
 c.inspect=function(actor,sector,macro)
  local function live()
   return C.IsValidComponent(actor) and C.IsComponentOperational(actor) and C.IsComponentClass(actor,'ship') and
    C.IsValidComponent(sector) and C.IsComponentClass(sector,'sector') and C.GetContextByClass(actor,'sector',false)==sector
  end
  if not c.guard() or not live() then return false end
  local a,s=ref(actor),ref(sector);if not a or not s then return false end
  local docked,docking,stored=data(a,'isdocked','isdocking','isinternallystored')
  if docked~=false or docking~=false or stored~=false or data(s,'macro')~=macro or not c.guard() or not live() then return false end
  local d,q,st=data(a,'isdocked','isdocking','isinternallystored')
  return d==false and q==false and st==false and data(s,'macro')==macro and c.guard() and live()
 end
 return M.new(c)
end
X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP=M
return M
