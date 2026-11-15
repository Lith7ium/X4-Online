-- Disposable opt-in probe, called only by the existing world-bridge update owner.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_resolve_string_native~=true then return end
local ffi=require('ffi')
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
ffi.cdef[[bool IsGamePaused(void);bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);
 bool IsComponentClass(UniverseID,const char*);const char* GetSaveFolderPath(void);]]
local C=ffi.C
local epoch=assert(cfg.authority_resolve_epoch);local id1=assert(cfg.authority_resolve_id1);local id2=assert(cfg.authority_resolve_id2)
local state='new';local failed=false;local paused_once=false;local started;local actor,actor_id,client
local expected_type='not_called'
local function log(s) DebugError('[X4LAN] AUTH_RESOLVE_STRING '..s) end
local function fail(s) if not failed then failed=true;state='failed';log('ERROR '..s) end end
local function guard()
 if failed then error('resolve v2 failed') end
 local p=C.GetSaveFolderPath()
 if p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=cfg.authority_resolve_save_path then
  fail('profile');error('invalid test profile')
 end
 if not C.IsGamePaused() then fail('pause_lost');error('pause lost') end
end
local function valid(v)
 local ok,converted=pcall(ConvertIDTo64Bit,v)
 if not ok then return false end
 local id=X4LAN_RESOLVE_STRING.actor_u64(converted)
 if not id or not actor_id or id~=actor_id then return false end
 return C.IsValidComponent(actor_id) and C.IsComponentOperational(actor_id) and C.IsComponentClass(actor_id,'ship')
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
RegisterEvent('X4AuthorityRegistryResolveString.Result',function(_,row)
 if failed then return end
 guard()
 local typ=type(row);local shape='absent';local length=0;local prefix='none'
 local id_match,epoch_match,index_match,status_match='unknown','unknown','unknown','unknown'
 if typ=='string' then
  local rid,rep_epoch,index,status=row:match('^([^|]*)|([^|]*)|([^|]*)|([^|]*)|[^|]*$')
  if rid then
   id_match=tostring(rid==(state=='ok' and id1 or id2))
   epoch_match=tostring(rep_epoch==epoch)
   index_match=tostring(index==(state=='ok' and '1' or '2'))
   status_match=tostring(status==(state=='ok' and 'ok' or 'unavailable'))
  end
  local tail=row:match('|([^|]+)$')
  if tail then
   length=#tail
   if tail:sub(1,2)=='0x' then prefix='0x' elseif tail:sub(1,2)=='0X' then prefix='0X' end
   local digits=tail:gsub('^0[xX]','')
   shape=digits:match('^[0-9a-fA-F]+$') and 'hex' or 'other'
  else shape='missing' end
 end
 log('SHAPE stage='..state..' type='..typ..' actor_format='..shape..' actor_length='..length..
  ' prefix='..prefix..' id_match='..id_match..' epoch_match='..epoch_match..
  ' index_match='..index_match..' status_match='..status_match)
 if state~='ok' and state~='unavailable' then fail('result_order');return end
 local ok,result=client:response(row)
 if state=='ok' then
  if not ok then
   local reasons={not_pending=true,clock=true,timeout=true,response=true,mismatch=true,
    unavailable_actor=true,unavailable=true,status=true,actor_hex=true,actor_mismatch=true,invalid_actor=true}
   log('REJECT stage=ok reason='..(reasons[result] and result or 'other')..' expected_type='..expected_type)
   fail('ok_response');return
  end
  if not valid(actor) then log('REJECT stage=ok reason=post_valid expected_type='..expected_type);fail('ok_response');return end
  log('ACTOR_MATCH');state='unavailable';assert(client:resolve(id2,2))
 else
  if ok or result~='unavailable' then
   local reasons={not_pending=true,clock=true,timeout=true,response=true,mismatch=true,
    unavailable_actor=true,unavailable=true,status=true,actor_hex=true,actor_mismatch=true,invalid_actor=true}
   log('REJECT stage=unavailable reason='..(not ok and reasons[result] and result or 'other'))
   fail('unavailable_response');return
  end
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
   if type(v)=='cdata' and ffi.istype('uint64_t',v) and e.operational(v) and e.is_ship(v) then
    actor_id=ffi.new('uint64_t',v)
    local k=e.key(v):gsub('ULL$','')
    if k:match('^[1-9]%d*$') then actor=ConvertStringToLuaID(k);if valid(actor) then return end end
    actor,actor_id=nil,nil
   end
  end
 end
 error('no existing operational ship')
end
function X4LAN_RESOLVE_STRING_NATIVE_READY()
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
  local selected=pcall(select_existing)
  if not selected then fail('selection');error('no safely matched fleet actor') end
  client=assert(X4LAN_RESOLVE_STRING.new({enabled=true,epoch=epoch,timeout=10,
   issue=send,clock=GetCurRealTime,
   expected_actor=function()
    if type(actor_id)=='cdata' and ffi.istype('uint64_t',actor_id) then expected_type='fleet_uint64'
    else expected_type='invalid_fleet_id';error('missing exact fleet actor ID') end
    return ffi.new('uint64_t',actor_id)
   end,
   valid=function() return valid(actor) end}))
  state='init';send('X4AuthorityShipRegistry','Initialize',{epoch=epoch})
 elseif state=='ok' or state=='unavailable' then
  local ok,why=client:tick();if not ok then fail('request_'..tostring(why));error('request failed') end
 end
 return state=='done'
end
