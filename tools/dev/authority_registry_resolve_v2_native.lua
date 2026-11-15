-- Disposable opt-in probe, called only by the existing world-bridge update owner.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_resolve_v2_native~=true then return end
local ffi=require('ffi')
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
ffi.cdef[[bool IsGamePaused(void);bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);
 bool IsComponentClass(UniverseID,const char*);const char* GetSaveFolderPath(void);]]
local C=ffi.C
local epoch=assert(cfg.authority_resolve_epoch);local id1=assert(cfg.authority_resolve_id1);local id2=assert(cfg.authority_resolve_id2)
local state='new';local failed=false;local paused_once=false;local started;local actor,actor_key,client
local function log(s) DebugError('[X4LAN] AUTH_RESOLVE_V2 '..s) end
local function fail(s) if not failed then failed=true;state='failed';log('ERROR '..s) end end
local function guard()
 if failed then error('resolve v2 failed') end
 local p=C.GetSaveFolderPath()
 if p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=cfg.authority_resolve_save_path then
  fail('profile');error('invalid test profile')
 end
 if not C.IsGamePaused() then fail('pause_lost');error('pause lost') end
end
local function key(v)
 local n=ConvertIDTo64Bit(v)
 if not n or n==0 then return nil end
 local s=tostring(n):gsub('ULL$','')
 if not s:match('^[1-9]%d*$') then return nil end
 return s
end
local function valid(v)
 local k=key(v);if not k or k~=actor_key then return false end
 local id=ffi.new('UniverseID',ConvertIDTo64Bit(v))
 return C.IsValidComponent(id) and C.IsComponentOperational(id) and C.IsComponentClass(id,'ship')
end
local function send(screen,op,args)
 guard()
 local issued=AddUITriggeredEvent(screen,op,args)
 if issued==false then fail('dispatch');error('MD dispatch rejected') end
 -- nil is an unconfirmed dispatch, never a receipt; the deadline still applies.
 return true
end
local function accept(expected)
 if failed then return false end
 guard();if state~=expected then fail('callback_order');return false end
 return true
end
RegisterEvent('X4AuthorityShipRegistry.Initialized',function(_,v)
 if not accept('init') then return end
 if v~=epoch then fail('registry_epoch');return end
 state='enroll';send('X4AuthorityShipRegistry','Enroll',{epoch=epoch,ship=actor})
end)
RegisterEvent('X4AuthorityShipRegistry.Enrolled',function(_,v)
 if not accept('enroll') then return end
 if tonumber(v)~=1 or not valid(actor) then fail('enrollment');return end
 state='ok';assert(client:resolve(id1,1))
end)
for _,event in ipairs({'Refused','Unavailable','Faulted','Uninitialized'}) do
 RegisterEvent('X4AuthorityShipRegistry.'..event,function() if not failed then fail('registry_'..event) end end)
end
RegisterEvent('X4AuthorityRegistryResolveV2.Result',function(_,row)
 if failed then return end
 guard()
 local typ=type(row);local names={};local actor_type='absent'
 if typ=='table' then
  for k in pairs(row) do
   if type(k)~='string' or not k:match('^%$?[%w_]+$') or #k>32 or #names>=12 then fail('unexpected_fields');return end
   names[#names+1]=k
  end
  table.sort(names);actor_type=type(row.actor)
 end
 log('SHAPE stage='..state..' type='..typ..' fields='..table.concat(names,',')..' actor_type='..actor_type)
 if state~='ok' and state~='unavailable' then fail('result_order');return end
 local ok,result=client:response(row)
 if state=='ok' then
  if not ok or not valid(result.actor) or result.local_key~=actor_key then fail('ok_response');return end
  log('ACTOR_MATCH');state='unavailable';assert(client:resolve(id2,2))
 else
  if ok or result~='unavailable' then fail('unavailable_response');return end
  log('UNAVAILABLE');state='done';log('DONE')
 end
end)
local function select_existing()
 local e=assert(X4LAN_AUTHORITY_SHIP_ENGINE).new()
 local factions,truncated=e.factions(1024);assert(not truncated and #factions>0)
 for _,f in ipairs(factions) do
  local n=e.fleet_count(f);assert(n>=0 and n<=200000 and n==math.floor(n))
  local ships,cut=e.fleet(f,n+1);assert(not cut and #ships==n and e.fleet_count(f)==n)
  for _,v in ipairs(ships) do
   guard()
   if e.operational(v) and e.is_ship(v) then
    local k=e.key(v):gsub('ULL$','')
    if k:match('^[1-9]%d*$') then actor=ConvertStringToLuaID(k);actor_key=k;if valid(actor) then return end end
   end
  end
 end
 error('no existing operational ship')
end
function X4LAN_RESOLVE_V2_NATIVE_READY()
 if failed then error('resolve v2 failed') end
 local now=GetCurRealTime();started=started or now
 if now-started>60 then fail('deadline');error('probe deadline') end
 if not C.IsGamePaused() then
  if state~='new' then fail('pause_lost');error('pause lost') end
  if not paused_once then paused_once=true;Pause() end
  return false
 end
 guard()
 if state=='new' then
  select_existing()
  client=assert(X4LAN_RESOLVE_V2.new({enabled=true,epoch=epoch,timeout=10,
   issue=send,clock=GetCurRealTime,valid=valid,key=key}))
  state='init';send('X4AuthorityShipRegistry','Initialize',{epoch=epoch})
 elseif state=='ok' or state=='unavailable' then
  local ok,why=client:tick();if not ok then fail('request_'..tostring(why));error('request failed') end
 end
 return state=='done'
end
