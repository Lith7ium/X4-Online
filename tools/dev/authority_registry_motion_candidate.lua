-- Experimental local-only selector. One existing owner routes Result and ticks.
-- The returned index is a momentary observation, not a reservation or proof
-- of cross-process identity; the source bootstrap must revalidate it.
local M={}
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function integer(v)return type(v)=='number' and v==v and v%1==0 and v>=1 and v<=200000 end
local function finite(v)return type(v)=='number' and v==v and v>=0 and v<math.huge end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 assert(token(c.epoch) and token(c.nonce) and integer(c.baseline) and finite(c.timeout) and c.timeout>0 and c.timeout<=120)
 assert(type(c.candidates)=='table' and #c.candidates>=1 and #c.candidates<=32)
 local indices,seen={},{}
 for i=1,#c.candidates do local n=c.candidates[i];assert(integer(n) and n<=c.baseline and not seen[n]);seen[n]=true;indices[i]=n end
 for _,k in ipairs({'clock','guard','issue','inspect'})do assert(type(c[k])=='function')end
 local state,busy='new',false;local current,last,deadline,result=0,nil,nil,nil
 local api={}
 local function fail()state='failed';return false end
 local function check()
  local before=state;local ok,t=pcall(c.clock)
  if not ok or state~=before or not finite(t) or (last and t<last) or (deadline and t>=deadline)then return false end
  last=t;local yes,good=pcall(c.guard)
  if not yes or good~=true or state~=before then return false end
  local again,u=pcall(c.clock)
  if not again or state~=before or not finite(u) or u<t or (deadline and u>=deadline)then return false end
  last=u;return true
 end
 local function finish(reason)
  state='done';result={status='inconclusive',reason=reason};return true
 end
 local function next_request()
  if current>=#indices then return finish('no_candidate')end
  current=current+1;state='waiting'
  local id=c.nonce:sub(1,16)..string.format('%016x',current)
  local ok,v=pcall(c.issue,'X4AuthorityRegistryMotionCandidate','Read',
   {epoch=c.epoch,count=c.baseline,index=indices[current],request_id=id})
  return ok and v==true and state=='waiting' and check()
 end
 function api:start()
  if busy or state~='new' then return fail()end
  busy=true;local ok=pcall(function()assert(check());deadline=last+c.timeout;assert(next_request())end)
  busy=false;if not ok then return fail()end;return true
 end
 function api:event(value)
  if busy or state~='waiting' then return fail()end
  busy=true;local ok=pcall(function()
   assert(check() and type(value)=='string' and #value<=256)
   local id,epoch,index,status,rest=value:match('^([0-9a-f]+)|([0-9a-f]+)|([0-9]+)|([a-z]+)|?(.*)$')
   assert(id==c.nonce:sub(1,16)..string.format('%016x',current) and epoch==c.epoch and index==string.format('%.0f',indices[current]))
   if status=='refused' and rest=='' then assert(finish('registry_refused'));return end
   if status=='ineligible' and rest=='' then assert(next_request());return end
   assert(status=='ok')
   local actor,sector,macro=rest:match('^(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([%w_%-]+)$')
   assert(actor and sector and #actor<=18 and #sector<=18 and #macro<=128)
   local yes,verdict=pcall(c.inspect,actor,sector,macro)
   assert(state=='waiting' and check())
   if not yes or verdict=='uncertain' then assert(finish('getter_or_context_unavailable'));return end
   if verdict=='ineligible' then assert(next_request());return end
   assert(verdict=='eligible')
   state='done';result={status='candidate',epoch=c.epoch,index=indices[current],runtime_reservation=false}
  end)
  busy=false;if not ok then return fail()end;return true
 end
 function api:tick()
  if busy or state~='waiting' then return fail()end
  busy=true;local ok=check();busy=false;if not ok then return fail()end;return true
 end
 function api:state()return state end
 function api:result()if state=='done' then return result end end
 return api
end
function M.new_x4(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 assert(type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save')
 assert(type(c.guard)=='function' and type(c.baseline_guard)=='function' and type(c.resolve)=='table' and c.resolve==X4LAN_RESOLVE_STRING)
 local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID')then ffi.cdef('typedef uint64_t UniverseID;')end
 ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);
 bool IsComponentClass(UniverseID,const char*);UniverseID GetContextByClass(UniverseID,const char*,bool);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local ext,base,path=c.guard,c.baseline_guard,c.expected_save_path
 local parse,u64=c.resolve.parse_hex,c.resolve.actor_u64
 local clock,trigger,data,to_lua,to64=GetCurRealTime,AddUITriggeredEvent,GetComponentData,ConvertStringToLuaID,ConvertIDTo64Bit
 assert(type(parse)=='function' and type(u64)=='function' and type(clock)=='function' and type(trigger)=='function' and type(data)=='function' and type(to_lua)=='function' and type(to64)=='function')
 local function environment()
  local p=C.GetSaveFolderPath()
  return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==path and C.IsPlayerValid() and not C.IsGamePaused()
 end
 c.clock=clock;c.guard=function()return environment() and ext()==true and base(c.epoch,c.baseline)==true and environment()end
 c.issue=function(screen,op,args)return trigger(screen,op,args)~=false end
 local function ref(id)
  local v=to_lua(tostring(id):gsub('ULL$',''));local kind=type(v)
  if kind=='number' or kind=='cdata' then if u64(v)~=id then return nil end
  elseif kind~='userdata' then return nil end
  if u64(to64(v))~=id then return nil end;return v
 end
 c.inspect=function(ah,sh,macro)
  local a,s=parse(ah),parse(sh);if not a or not s then return 'uncertain' end
  local function live()
   return c.guard() and C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and
    C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s
  end
  if not live()then return 'uncertain'end
  local ar,sr=ref(a),ref(s);if not ar or not sr then return 'uncertain'end
  local function read()
   local docked,docking,stored=data(ar,'isdocked','isdocking','isinternallystored')
   if type(docked)~='boolean' or type(docking)~='boolean' or type(stored)~='boolean' or data(sr,'macro')~=macro then return 'uncertain'end
   if docked or docking or stored then return 'ineligible'end
   return 'eligible'
  end
  local first=read();if first=='uncertain' or not live()then return 'uncertain'end
  local second=read();if first~=second or not live()then return 'uncertain'end
  return second
 end
 return M.new(c)
end
X4LAN_AUTHORITY_REGISTRY_MOTION_CANDIDATE=M
return M
