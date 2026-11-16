-- Default-off, read-only local observer. Caller owns all events and onUpdate.
-- No Pause/Unpause, input injection, coordinate setter, save or transport.
local M={}
local function token(s)return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function hex(s)return type(s)=='string' and #s<=18 and s:match('^0[xX][0-9a-fA-F]+$')~=nil end
local labels={'neutral','before','after'}
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.nonce) and finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,n in ipairs({'guard','issue','inspect','confirmed'})do assert(type(o[n])=='function')end
 local phase='new';local busy,failed=false,false;local started,last_t,last_g,paused_game;local next_seq=1;local pending,previous
 local api={}
 local function fault()failed=true;phase='failed';return false,'fault'end
 local function check()
  local t,g,paused=o.guard();assert(finite(t) and t>=0 and finite(g) and g>=0 and type(paused)=='boolean' and
   (not last_t or t>=last_t) and (not last_g or g>=last_g))
  started=started or t;last_t,last_g=t,g;assert(t-started<o.timeout)
  if phase=='armed' then assert(paused and g==paused_game)
  elseif phase=='await_running' and paused then assert(g==paused_game)
  elseif phase=='ready' or phase=='waiting' or phase=='done' then assert(not paused and g>paused_game) end
  return t,g,paused
 end
 local function run(fn)
  if failed or busy then return fault()end;busy=true
  local ok,value=pcall(function()local t,g,p=check();local r=fn(t,g,p);assert(not failed);check();return r end);busy=false
  if not ok or failed then return fault()end;return true,value
 end
 function api:arm()
  return run(function(_,g,p)assert(phase=='new' and p and o.confirmed()==true and not failed);paused_game=g;phase='armed'end)
 end
 function api:begin_resume()
  return run(function(_,g,p)assert(phase=='armed' and p and g==paused_game);phase='await_running'end)
 end
 function api:tick()
  return run(function(_,g,p)
   if phase=='await_running' and not p and g>paused_game then phase='ready'
   else assert(phase=='armed' or phase=='await_running' or phase=='ready' or phase=='waiting' or phase=='done')end
  end)
 end
 function api:request(label)
  return run(function()
   assert(phase=='ready' and next_seq<=3 and label==labels[next_seq]);pending=next_seq;phase='waiting'
   assert(o.issue('X4AuthorityPlayerFlightObserver','Read',{epoch=o.epoch,request_id=o.nonce,seq=pending})==true)
  end)
 end
 function api:response(v)
  return run(function(t0,g0)
   assert(phase=='waiting' and type(v)=='string' and #v<=256)
   local n,e,seq,a,s,z,owner=v:match('^([0-9a-f]+)|([0-9a-f]+)|([123])|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([%w_.%-]+)$')
   assert(n==o.nonce and e==o.epoch and seq==tostring(pending) and hex(a) and hex(s) and hex(z) and #owner<=128)
   local x=o.inspect(a,s,z,owner);assert(not failed and type(x)=='table')
   local t1,g1,p1=check();assert(not p1)
   for _,k in ipairs({'real_before','real_after','game_before','game_after','x','y','z','yaw','pitch','roll'})do assert(finite(x[k]))end
   assert(x.real_before>=t0 and x.real_after>=x.real_before and t1>=x.real_after and x.game_before>=g0 and x.game_after>=x.game_before and g1>=x.game_after and x.game_before>paused_game)
   if previous then assert(x.real_before>previous.real_after and x.game_before>previous.game_after)end
   previous={real_after=x.real_after,game_after=x.game_after}
   local result={sequence=pending,label=labels[pending],real_before=x.real_before,real_after=x.real_after,
    game_before=x.game_before,game_after=x.game_after,x=x.x,y=x.y,z=x.z,yaw=x.yaw,pitch=x.pitch,roll=x.roll,
    movement_cause_proven=false,input_proven=false,multiplayer_proven=false}
   next_seq=next_seq+1;pending=nil;phase=next_seq==4 and 'done' or 'ready';return result
  end)
 end
 function api:refused()return fault()end
 function api:close()if phase~='done' then return fault()end;phase='closed';return true end
 function api:state()return phase end
 return api
end
function M.new_x4(cfg)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 assert(type(cfg.expected_save_path)=='string' and cfg.expected_save_path:sub(1,1)=='/' and cfg.expected_save_path:sub(-11)=='/45841/save')
 assert(type(cfg.confirmed)=='function' and type(cfg.external_guard)=='function')
 assert(type(cfg.owner_id)=='string' and #cfg.owner_id>0 and #cfg.owner_id<=128 and cfg.owner_id:match('^[%w_.%-]+$'))
 for _,n in ipairs({'GetCurRealTime','AddUITriggeredEvent','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'})do assert(type(_G[n])=='function')end
 assert(type(X4LAN_RESOLVE_STRING)=='table' and type(X4LAN_RESOLVE_STRING.parse_hex)=='function' and type(X4LAN_RESOLVE_STRING.actor_u64)=='function')
 local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID')then ffi.cdef('typedef uint64_t UniverseID;')end
 if not pcall(ffi.typeof,'UIPosRot')then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;')end
 ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);double GetCurrentGameTime(void);
 UniverseID GetPlayerContainerID(void);UniverseID GetPlayerOccupiedShipID(void);UniverseID GetPlayerControlledShipID(void);
 UIPosRot GetObjectPositionInSector(UniverseID);const char* GetSaveFolderPath(void);]]
 assert(type(cfg.target)=='cdata' and type(cfg.sector)=='cdata' and type(cfg.parent_zone)=='cdata')
 local C=ffi.C;local actor=X4LAN_RESOLVE_STRING.actor_u64(cfg.target);local sector=X4LAN_RESOLVE_STRING.actor_u64(cfg.sector)
 local zone=X4LAN_RESOLVE_STRING.actor_u64(cfg.parent_zone);assert(actor and sector and zone)
 local idtext=(tostring(actor):gsub('ULL$',''));local id=ConvertStringToLuaID(idtext);assert(id~=nil and id~=false)
 assert(tostring(ConvertIDTo64Bit(id)):gsub('ULL$','')==idtext)
 local o={};for k,v in pairs(cfg)do o[k]=v end
 o.guard=function()
  local t0=GetCurRealTime();local path=C.GetSaveFolderPath();local paused=C.IsGamePaused()
  assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.expected_save_path and C.IsPlayerValid())
  assert(cfg.external_guard()==true and C.IsValidComponent(actor) and C.IsComponentOperational(actor) and C.IsComponentClass(actor,'ship') and
   C.IsValidComponent(sector) and C.IsComponentClass(sector,'sector') and C.IsValidComponent(zone) and C.IsComponentClass(zone,'zone') and
   C.GetContextByClass(actor,'sector',false)==sector and C.GetContextByClass(actor,'zone',false)==zone and
   C.GetPlayerContainerID()==actor and C.GetPlayerOccupiedShipID()==actor and C.GetPlayerControlledShipID()==actor)
  local owner=GetComponentData(id,'owner');assert(type(owner)=='string' and owner==cfg.owner_id)
  local g=tonumber(C.GetCurrentGameTime());local t=GetCurRealTime()
  assert(finite(t0) and finite(t) and t>=t0 and C.IsGamePaused()==paused);return t,g,paused
 end
 o.issue=function(screen,operation,args)return AddUITriggeredEvent(screen,operation,args)~=false end
 o.inspect=function(ah,sh,zh,owner)
  assert(X4LAN_RESOLVE_STRING.parse_hex(ah)==actor and X4LAN_RESOLVE_STRING.parse_hex(sh)==sector and
   X4LAN_RESOLVE_STRING.parse_hex(zh)==zone and owner==cfg.owner_id)
  o.guard();local rb=GetCurRealTime();local gb=tonumber(C.GetCurrentGameTime())
  local p=C.GetObjectPositionInSector(actor)
  local ga=tonumber(C.GetCurrentGameTime());local ra=GetCurRealTime();o.guard()
  return {real_before=rb,real_after=ra,game_before=gb,game_after=ga,
   x=tonumber(p.x),y=tonumber(p.y),z=tonumber(p.z),yaw=tonumber(p.yaw),pitch=tonumber(p.pitch),roll=tonumber(p.roll)}
 end
 return M.new(o)
end
X4LAN_AUTHORITY_PLAYER_FLIGHT_OBSERVER=M
return M
