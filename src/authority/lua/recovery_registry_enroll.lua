-- Disposable recovery-server bootstrap. Candidates are local handles, never wire IDs.
-- This owner requires a paused source and an exclusive, correlated event route.
local M={}
local SCREEN='X4AuthorityShipRegistry'
local function hex(v) return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$') end
function M.new(o)
 assert(type(o)=='table' and o.enabled==true and hex(o.epoch) and hex(o.nonce) and o.epoch~=o.nonce)
 assert(type(o.limit)=='number' and o.limit%1==0 and o.limit>=1 and o.limit<=200000)
 for _,k in ipairs({'clock','paused','issue','key','to_md_actor','from_md_actor','valid','candidates','complete'}) do assert(type(o[k])=='function',k) end
 assert(type(o.registry)=='table' and type(o.registry.new)=='function')
 local state='new';local deadline;local seen={};local actors;local index=1;local result;local client;local last
 local function fail() state='failed';if client then client:close() end;return false end
 local function guard()
  local t=o.clock()
  if type(t)~='number' or t~=t or t<0 or t==math.huge or (last and t<last) or o.paused()~=true or (deadline and t>=deadline) then return false end
  last=t;return true
 end
 local function finish(op,value)
  if result or not guard() then return false end
  result={op,value};return true
 end
 local api={}
 function api:start()
  if state~='new' or not guard() then return fail() end
  state='preflight';deadline=last+30
  if o.issue(SCREEN,'Status',{request_id=o.nonce..':0'})~=true or state~='preflight' then return fail() end
  return true
 end
 function api:event(value)
  if not guard() then return fail() end
  if state=='preflight' then
   if value~=o.nonce..':0|Uninitialized|' then return fail() end
   deadline=nil;state='inventory';return true
  end
  if not client or state=='new' or state=='inventory' or state=='done' or state=='failed' then return fail() end
  if not client:on_event('Correlated',value) then return fail() end
  return true
 end
 function api:tick()
  if state=='failed' or not guard() then return fail() end
  if state=='done' then return true end
  if state=='inventory' then
   local phase,items=o.candidates()
   if phase=='running' then return true end
   if phase~='done' or type(items)~='table' or #items<1 or #items>o.limit then return fail() end
   for k in pairs(items) do if type(k)~='number' or k%1~=0 or k<1 or k>#items then return fail() end end
   for _,actor in ipairs(items) do
    if o.valid(actor)~=true then return fail() end
    local key=o.key(actor);if type(key)~='string' or key=='' or seen[key] then return fail() end
    seen[key]=true
   end
   actors=items
   client=assert(o.registry.new({enabled=true,epoch=o.epoch,correlation_nonce=o.nonce,timeout=30,
    clock=o.clock,issue=o.issue,key=o.key,to_md_actor=o.to_md_actor,from_md_actor=o.from_md_actor,
    valid=o.valid,complete=finish}))
   state='init_wait';if not client:initialize() then return fail() end
  elseif client then
   if not client:tick() then return fail() end
   if result then
    local op,value=result[1],result[2];result=nil
    if state=='init_wait' and op=='Initialize' and value==o.epoch then state='enroll'
    elseif state=='enroll_wait' and op=='Enroll' and value==index then state='resolve'
    elseif state=='resolve_wait' and op=='Resolve' and o.key(value)==o.key(actors[index]) then state='repeat'
    elseif state=='repeat_wait' and op=='Enroll' and value==index then index=index+1;state='enroll'
    else return fail() end
   end
   if state=='enroll' then
    if index>#actors then
     state='done';client:close()
     if o.complete(o.epoch,#actors)~=true or not guard() then return fail() end
    else state='enroll_wait';if not client:enroll(actors[index]) then return fail() end end
   elseif state=='resolve' then state='resolve_wait';if not client:resolve(index) then return fail() end
   elseif state=='repeat' then state='repeat_wait';if not client:enroll(actors[index]) then return fail() end end
  end
  return true
 end
 function api:state() return state end
 return api
end
-- Isolated X4 binding. It samples the same faction lists as the earlier
-- census experiment. Membership is not proof of whole-universe coverage.
function M.new_x4(cfg)
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 ffi.cdef[[const char* GetSaveFolderPath(void);bool IsGamePaused(void);bool IsPlayerValid(void);
 bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);]]
 local C=ffi.C;local resolver=assert(X4LAN_RESOLVE_STRING)
 local function guard()
  local path=C.GetSaveFolderPath()
  return path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.expected_save_path
   and C.IsPlayerValid() and C.IsGamePaused()
 end
 local function actor(v)
  if type(v)=='cdata' then return resolver.actor_u64(v) end
  local ok,n=pcall(ConvertIDTo64Bit,v);if not ok then return nil end
  return resolver.actor_u64(n)
 end
 local function key(v)
  local n=actor(v);if not n then return nil end
  local s=tostring(n):gsub('ULL$','');if not s:match('^[1-9]%d*$') then return nil end;return s
 end
 local function valid(v)
  local n=actor(v)
  return guard() and n~=nil and C.IsValidComponent(n) and C.IsComponentOperational(n) and C.IsComponentClass(n,'ship') and guard()
 end
 local function inventory()
  local e=assert(X4LAN_AUTHORITY_SHIP_ENGINE).new()
  local factions,cut=e.factions(1024);assert(not cut and #factions>0 and #factions<1024)
  local seen,chosen={},{};local enumerated,eligible=0,0
  for _,f in ipairs(factions) do
   assert(guard());local count=e.fleet_count(f);assert(count>=0 and count<=200000 and count%1==0)
   local ships,truncated=e.fleet(f,count+1)
   assert(not truncated and #ships==count and e.fleet_count(f)==count)
   for _,ship in ipairs(ships) do
    assert(guard());enumerated=enumerated+1
    if enumerated%256==0 then coroutine.yield() end
    local k=key(ship);assert(k)
    if not seen[k] then
     seen[k]=true
     if valid(ship) and e.sector(ship) then
      eligible=eligible+1
      if #chosen<cfg.limit then chosen[#chosen+1]=ship end
     end
    end
   end
  end
  assert(guard() and #chosen>0)
  DebugError('[X4LAN] AUTH_RECOVERY_ENROLL_INVENTORY selected='..#chosen..' eligible='..eligible..' enumerated='..enumerated..' coverage=unknown')
  return chosen
 end
 local task=coroutine.create(inventory)
 local opts={enabled=true,epoch=cfg.epoch,nonce=cfg.nonce,limit=cfg.limit,registry=assert(X4LAN_SHIP_REGISTRY_CLIENT),
  clock=GetCurRealTime,paused=guard,issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end,
  valid=valid,key=key,to_md_actor=function(_,k)return ConvertStringToLuaID(k)end,
  from_md_actor=function(s)return resolver.parse_hex(s)end,complete=cfg.complete,
  candidates=function()
   local ok,v=coroutine.resume(task);assert(ok,v)
   if coroutine.status(task)=='dead' then return 'done',v end
   return 'running'
  end}
 return M.new(opts)
end
X4LAN_RECOVERY_REGISTRY_ENROLL=M
return M
