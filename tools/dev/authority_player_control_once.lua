-- Default-off private single-player takeover diagnostic; no event/update owner installed.
local M={}
local function token(s)return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function hex(s)return type(s)=='string' and #s<=18 and s:match('^0[xX][0-9a-fA-F]+$')~=nil end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.nonce) and finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,n in ipairs({'guard','issue','validate','inspect'}) do assert(type(o[n])=='function') end
 local phase='new';local mode='pre';local failed=false;local busy=false;local t0,last,pre_game,post_game,target,sector,owner
 local api={};local expired=false;local done
 local function fault() failed=true;phase='failed';return false,'fault' end
 local function check(enforce_deadline)
  local t,g=o.guard(mode);assert(finite(t) and t>=0 and finite(g) and g>=0 and (not last or t>=last))
  t0=t0 or t;last=t
  if mode=='pre' then pre_game=pre_game or g;assert(pre_game==g)
  else post_game=post_game or g;assert(post_game==g) end
  if target then
   assert(o.validate(target,sector,owner)==true)
   local t2,g2=o.guard(mode);assert(finite(t2) and t2>=last and finite(g2) and g2==g)
   last=t2;t=t2
  end
  if enforce_deadline and t-t0>=o.timeout then expired=true end
 end
 local function run(fn,is_tick)
  if failed or busy then return fault() end
  local enforce_deadline=phase~='done'
  busy=true;local ok,value=pcall(function()
   check(enforce_deadline)
   if expired then if is_tick then return done('inconclusive') else error('late event') end end
   local r=fn();assert(not failed);check(enforce_deadline)
   if expired then return done('inconclusive') end;return r
  end);busy=false
  if not ok or failed then return fault() end;return true,value
 end
 local function issue(op,seq)
  local args={epoch=o.epoch,request_id=o.nonce};if seq~=nil then args.seq=seq end
  assert(o.issue('X4AuthorityPlayerControlOnce',op,args)==true)
 end
 done=function(status)
  phase='done';expired=false;return {status=status,local_control_proven=status=='controlled',flight_proven=false,
   seat_free_proven=false,multiplayer_proven=false,save_authorized=false}
 end
 function api:tick()
  if phase=='done' then return run(function()return nil end) end
  return run(function()
   if phase=='new' then phase='creating';issue('Create')
   elseif phase=='read_pre' then phase='waiting_pre';issue('Read',0)
   elseif phase=='teleport' then
    -- Before issue: deliberately leave the old player-context guard; retain the
    -- global paused/process guard and establish a new post-teleport time baseline.
    mode='post';phase='dispatching';check(true);if not expired then issue('Teleport') end
   elseif phase=='read_one' then phase='waiting_one';issue('Read',1)
   elseif phase=='read_two' then phase='waiting_two';issue('Read',2)
   else assert(phase=='creating' or phase=='waiting_pre' or phase=='dispatching' or phase=='waiting_one' or phase=='waiting_two') end
  end,true)
 end
 function api:created(v)
  return run(function()
   assert(phase=='creating' and type(v)=='string' and #v<=160)
   local n,e,a,s=v:match('^([0-9a-f]+)|([0-9a-f]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)$')
   assert(n==o.nonce and e==o.epoch and hex(a) and hex(s));target,sector=a,s;phase='read_pre'
  end)
 end
 function api:dispatched(v)
  return run(function()assert(phase=='dispatching' and v==o.nonce..'|'..o.epoch);phase='read_one'end)
 end
 function api:response(v)
  return run(function()
   assert((phase=='waiting_pre' or phase=='waiting_one' or phase=='waiting_two') and type(v)=='string' and #v<=256)
   local n,e,seq,a,s,p,oc,c,sec,own,oid=v:match('^([0-9a-f]+)|([0-9a-f]+)|([012])|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([01])|([01])|([01])|([01])|([01])|([%w_.%-]+)$')
   local expected=phase=='waiting_pre' and '0' or phase=='waiting_one' and '1' or '2'
   assert(n==o.nonce and e==o.epoch and seq==expected and a==target and s==sector and own=='1' and #oid<=128)
   if owner then assert(owner==oid) else owner=oid end
   local flags={p=='1',oc=='1',c=='1',sec=='1'}
   assert(o.inspect(target,sector,flags,owner)==true)
   if expected=='0' then assert(not flags[1] and not flags[2] and not flags[3]);phase='teleport'
   elseif not (flags[1] and flags[2] and flags[3] and flags[4]) then return done('inconclusive')
   elseif expected=='1' then phase='read_two'
   else return done('controlled') end
  end)
 end
 function api:refused() return fault() end
 function api:state()return phase end
 return api
end
function M.new_x4(cfg)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 assert(type(cfg.expected_save_path)=='string' and cfg.expected_save_path:sub(1,1)=='/' and cfg.expected_save_path:sub(-11)=='/45841/save')
 assert(type(cfg.pre_guard)=='function' and type(cfg.post_guard)=='function')
 for _,n in ipairs({'GetCurRealTime','AddUITriggeredEvent','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'}) do assert(type(_G[n])=='function') end
 assert(type(X4LAN_RESOLVE_STRING)=='table' and type(X4LAN_RESOLVE_STRING.parse_hex)=='function')
 local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);double GetCurrentGameTime(void);
 UniverseID GetPlayerContainerID(void);UniverseID GetPlayerOccupiedShipID(void);UniverseID GetPlayerControlledShipID(void);
 const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local o={};for k,v in pairs(cfg) do o[k]=v end
 local function resolve(a,s)
  local actor=X4LAN_RESOLVE_STRING.parse_hex(a);local sector=X4LAN_RESOLVE_STRING.parse_hex(s)
  assert(actor and sector and C.IsValidComponent(actor) and C.IsComponentOperational(actor) and C.IsComponentClass(actor,'ship') and
   C.IsValidComponent(sector) and C.IsComponentClass(sector,'sector') and C.GetContextByClass(actor,'sector',false)==sector)
  local key=tostring(actor):gsub('ULL$','');local id=ConvertStringToLuaID(key);assert(id~=nil and id~=false)
  local back=ConvertIDTo64Bit(id);assert(tostring(back):gsub('ULL$','')==key)
  return actor,sector,id
 end
 o.guard=function(mode)
  local before=GetCurRealTime();local path=C.GetSaveFolderPath()
  assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.expected_save_path)
  assert(C.IsPlayerValid() and C.IsGamePaused())
  if mode=='pre' then assert(cfg.pre_guard()==true) else assert(mode=='post' and cfg.post_guard()==true) end
  local g=tonumber(C.GetCurrentGameTime());local after=GetCurRealTime()
  assert(finite(before) and finite(after) and after>=before and C.IsGamePaused());return after,g
 end
 o.issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end
 o.validate=function(a,s,owner)
  local _,_,id=resolve(a,s);local dock,docking,stored=GetComponentData(id,'isdocked','isdocking','isinternallystored')
  assert(dock==false and docking==false and stored==false)
  if owner then local found=GetComponentData(id,'owner');assert(type(found)=='string' and found==owner) end
  return true
 end
 o.inspect=function(a,s,flags,owner)
  local actor,sector,id=resolve(a,s);local actual_owner=GetComponentData(id,'owner');assert(type(actual_owner)=='string' and actual_owner==owner)
  local container=C.GetPlayerContainerID();assert(container~=0 and C.IsValidComponent(container))
  local matches={C.GetContextByClass(container,'ship',true)==actor,C.GetPlayerOccupiedShipID()==actor,
   C.GetPlayerControlledShipID()==actor,C.GetContextByClass(container,'sector',true)==sector}
  for i=1,4 do assert(matches[i]==flags[i]) end
  assert(C.IsGamePaused());resolve(a,s);return true
 end
 return M.new(o)
end
X4LAN_AUTHORITY_PLAYER_CONTROL_ONCE=M
return M
