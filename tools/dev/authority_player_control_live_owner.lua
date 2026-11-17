-- Private opt-in owner; the existing load callback is the sole onUpdate source.
local M={}
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,n in ipairs({'guard','make','target','log'})do assert(type(o[n])=='function')end
 local busy,failed=false,false;local phase='new';local mode='pre';local target,locked,probe,outcome
 local start,last,pre_game,post_game
 local function fail()if not failed then failed=true;phase='failed';pcall(o.log,'ERROR FAULT')end;return false end
 local function checked()
  local t,g=o.guard(mode,target,locked);assert(finite(t) and finite(g) and t>=0 and g>=0 and (not last or t>=last))
  start=start or t;last=t;assert(t-start<o.timeout)
  if mode=='pre' then pre_game=pre_game or g;assert(pre_game==g) else post_game=post_game or g;assert(post_game==g and pre_game==g)end
 end
 local function action(fn)
  if failed or busy then return fail()end;busy=true
  local ok=pcall(function()checked();fn();assert(not failed);checked()end);busy=false
  if not ok or failed then return fail()end;return true
 end
 local function pre_guard()checked();return true end
 local function post_guard()if mode=='pre'then mode='post'end;checked();return true end
 local function record(r)
  assert(type(r)=='table' and (r.status=='controlled' or r.status=='inconclusive') and
   r.local_control_proven==(r.status=='controlled') and r.flight_proven==false and
   r.seat_free_proven==false and r.multiplayer_proven==false and r.save_authorized==false)
  outcome=r.status;phase='report'
 end
 local api={}
 function api:tick()
  return action(function()
   if phase=='new'then
    probe=o.make(pre_guard,post_guard);assert(probe);phase='active';local ok,r=probe:tick();assert(ok and not failed)
    o.log('START');if r then record(r)end
   elseif phase=='active'then
    local ok,r=probe:tick();assert(ok and not failed);if r then record(r)end
   elseif phase=='report'then
    checked();phase='done';o.log(outcome=='controlled' and 'CONTROLLED' or 'INCONCLUSIVE');o.log('DONE')
   else assert(phase=='done')end
  end)
 end
 function api:created(v)
  return action(function()
   assert(phase=='active' and probe:state()=='creating' and not target)
   target=o.target(v);assert(target);local ok,r=probe:created(v);assert(ok and not failed);o.log('CREATED');if r then record(r)end
  end)
 end
 function api:dispatched(v)
  return action(function()
   assert(phase=='active' and probe:state()=='dispatching');local ok,r=probe:dispatched(v);assert(ok and not failed)
   o.log('DISPATCH');if r then record(r)end
  end)
 end
 function api:response(v)
  return action(function()
   assert(phase=='active');local prior=probe:state();assert(prior=='waiting_pre' or prior=='waiting_one' or prior=='waiting_two')
   local ok,r=probe:response(v);assert(ok and not failed)
   if prior=='waiting_pre' and probe:state()=='teleport' then o.log('BEFORE')
   elseif prior=='waiting_pre' and probe:state()=='read_one' then o.log('EXISTING')
   elseif prior=='waiting_one' and probe:state()=='read_two' then locked=true;checked();o.log('FIRST')end
   if r then record(r)end
  end)
 end
 function api:refused()return fail()end
 function api:state()return phase end
 return api
end
X4LAN_AUTHORITY_PLAYER_CONTROL_LIVE_OWNER=M
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_player_control_live~=true then return M end
local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID')then ffi.cdef('typedef uint64_t UniverseID;')end
ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);double GetCurrentGameTime(void);
 UniverseID GetPlayerContainerID(void);UniverseID GetPlayerOccupiedShipID(void);UniverseID GetPlayerControlledShipID(void);
 const char* GetSaveFolderPath(void);]]
local C=ffi.C;local old,old_npc,old_sector
local function context()
 local container=C.GetPlayerContainerID();assert(container~=0 and C.IsValidComponent(container))
 local sector=C.GetContextByClass(container,'sector',true);assert(sector~=0 and C.IsValidComponent(sector) and C.IsComponentClass(sector,'sector'))
 return {container=container,sector=sector,ship=C.GetContextByClass(container,'ship',true),
  occupied=C.GetPlayerOccupiedShipID(),controlled=C.GetPlayerControlledShipID()}
end
local function equal(a,b)return a.container==b.container and a.sector==b.sector and a.ship==b.ship and a.occupied==b.occupied and a.controlled==b.controlled end
local function one_of(x,a,b)return x==a or x==b or x==0 end
local function guard(mode,target,locked)
 local before=GetCurRealTime();local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 assert(C.IsPlayerValid() and C.IsGamePaused());local now=context()
 if not old then
  local a,s=X4LAN_SECTOR_READ_EXPORT();assert(a~=0 and s~=0);old,old_npc,old_sector=now,a,s
 end
 if mode=='pre'then
  local a,s=X4LAN_SECTOR_READ_EXPORT()
  assert(a==old_npc and s==old_sector and equal(now,old) and C.IsValidComponent(a) and C.IsComponentOperational(a) and
   C.IsComponentClass(a,'ship') and C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s)
 else
  assert(mode=='post' and target and C.IsValidComponent(target.ship) and C.IsComponentOperational(target.ship) and
   C.IsComponentClass(target.ship,'ship') and C.GetContextByClass(target.ship,'sector',false)==target.sector)
  assert((now.container==old.container or now.container==target.ship) and (now.sector==old.sector or now.sector==target.sector) and
   one_of(now.ship,old.ship,target.ship) and one_of(now.occupied,old.occupied,target.ship) and one_of(now.controlled,old.controlled,target.ship))
  if locked then assert(now.container==target.ship and now.sector==target.sector and now.ship==target.ship and now.occupied==target.ship and now.controlled==target.ship)end
 end
 local g=tonumber(C.GetCurrentGameTime());local after=GetCurRealTime()
 assert(finite(before) and finite(after) and after>=before and C.IsGamePaused());return after,g
end
local function target(v)
 assert(type(v)=='string' and #v<=160)
 local n,e,a,s=v:match('^([0-9a-f]+)|([0-9a-f]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)$')
 assert(n==cfg.authority_player_control_nonce and e==cfg.authority_sector_epoch)
 local ship=X4LAN_RESOLVE_STRING.parse_hex(a);local sector=X4LAN_RESOLVE_STRING.parse_hex(s)
 assert(ship and sector and C.IsValidComponent(ship) and C.IsComponentOperational(ship) and C.IsComponentClass(ship,'ship') and
  C.IsValidComponent(sector) and C.IsComponentClass(sector,'sector') and C.GetContextByClass(ship,'sector',false)==sector and ship~=old.container and ship~=old.ship and ship~=old.occupied and ship~=old.controlled)
 return {ship=ship,sector=sector}
end
local app=M.new{enabled=true,timeout=cfg.authority_player_control_timeout,guard=guard,target=target,
 make=function(pre,post)return X4LAN_AUTHORITY_PLAYER_CONTROL_ONCE.new_x4{enabled=true,epoch=cfg.authority_sector_epoch,
  nonce=cfg.authority_player_control_nonce,timeout=math.min(10,cfg.authority_player_control_timeout/2),
  expected_save_path=cfg.authority_read_save_path,pre_guard=pre,post_guard=post,
  teleport_phase=function(s)assert(s=='INTENT_TELEPORT' or s=='LOCAL_CALL_RETURNED');DebugError('[X4LAN] AUTH_PLAYER_CONTROL_LIVE '..s)end}end,
 log=function(s)DebugError('[X4LAN] AUTH_PLAYER_CONTROL_LIVE '..s)end}
RegisterEvent('X4AuthorityPlayerControlOnce.Created',function(_,v)app:created(v)end)
RegisterEvent('X4AuthorityPlayerControlOnce.Dispatched',function(_,v)app:dispatched(v)end)
RegisterEvent('X4AuthorityPlayerControlOnce.ReadResult',function(_,v)app:response(v)end)
RegisterEvent('X4AuthorityPlayerControlOnce.Refused',function()app:refused()end)
function X4LAN_PLAYER_CONTROL_LIVE_TICK()if not app:tick()then error('player control probe failed')end end
return M
