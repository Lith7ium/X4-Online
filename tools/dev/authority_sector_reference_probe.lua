-- Disposable, opt-in gate. Caller invokes READY only through an existing update owner.
local cfg=X4LAN_CONFIG
if not cfg or not cfg.authority_sector_phase then return end
local phase=cfg.authority_sector_phase
assert(phase=='save' or phase=='load')
local ffi=require('ffi');ffi.cdef[[bool IsGamePaused(void);]]
local C=ffi.C
local registry='X4AuthorityShipRegistry'
local fixture='X4AuthoritySectorReferenceFixture'
local epoch=assert(cfg.authority_sector_epoch)
assert(type(epoch)=='string' and #epoch==32 and epoch:match('^[0-9a-f]+$'))
local state='new';local failed=false;local started=nil;local requested_pause=false
local actors={};local scan=nil;local seen_epoch=false
local function log(s) DebugError('[X4LAN] AUTH_SECTOR '..phase..' '..s) end
local function fail(s) if not failed then failed=true;state='failed';log('ERROR '..s) end end
local function guard()
 if failed then error('sector experiment failed') end
 if not C.IsGamePaused() then fail('pause_lost');error('sector experiment lost pause') end
end
local function send(screen,op,args)
 guard();AddUITriggeredEvent(screen,op,args)
end
local function accept(expected)
 if failed then return false end
 guard()
 if state~=expected then fail('unexpected_callback');return false end
 return true
end
RegisterEvent(registry..'.Initialized',function(_,v)
 if not accept('initialize') then return end
 if v~=epoch then fail('initialize_epoch');return end
 state='enroll1';send(registry,'Enroll',{epoch=epoch,ship=actors[1]})
end)
RegisterEvent(registry..'.Enrolled',function(_,v)
 if failed then return end
 guard()
 if state=='enroll1' and tonumber(v)==1 then
  state='enroll2';send(registry,'Enroll',{epoch=epoch,ship=actors[2]})
 elseif state=='enroll2' and tonumber(v)==2 then
  state='fixture';send(fixture,'Initialize',{epoch=epoch,index1=1,index2=2})
 else fail('enrollment') end
end)
RegisterEvent(registry..'.Epoch',function(_,v)
 if not accept('status') then return end
 if seen_epoch or v~=epoch then fail('status_epoch');return end
 seen_epoch=true
end)
RegisterEvent(registry..'.Count',function(_,v)
 if not accept('status') then return end
 if not seen_epoch or tonumber(v)~=2 then fail('status_count');return end
 state='verify';send(fixture,'Verify',{epoch=epoch})
end)
RegisterEvent(fixture..'.Initialized',function(_,v)
 if not accept('fixture') then return end
 if v~=epoch then fail('fixture_epoch');return end
 state='verify';send(fixture,'Verify',{epoch=epoch})
end)
RegisterEvent(fixture..'.Verified',function(_,v)
 if not accept('verify') then return end
 if v~=epoch then fail('verify_epoch');return end
 state='done';log('VERIFIED '..epoch..' slots=2')
end)
for _,event in ipairs({'Refused','Unavailable','Faulted','Uninitialized'}) do
 RegisterEvent(registry..'.'..event,function() if not failed then fail('registry_'..event) end end)
end
RegisterEvent(fixture..'.Refused',function() if not failed then fail('fixture_refused') end end)
local function select_existing()
 local engine=assert(X4LAN_AUTHORITY_SHIP_ENGINE).new()
 local factions,truncated=engine.factions(1024)
 assert(not truncated and #factions>0,'faction enumeration')
 local seen_ships={};local selected_sector={}
 for _,faction in ipairs(factions) do
  local count=engine.fleet_count(faction)
  assert(count>=0 and count<=200000 and count==math.floor(count),'fleet count')
  local ships,cut=engine.fleet(faction,count+1)
  assert(not cut and #ships==count and engine.fleet_count(faction)==count,'fleet changed')
  for _,ship in ipairs(ships) do
   guard()
   local key=engine.key(ship)
   assert(key~='','invalid actor')
   if not seen_ships[key] then
    seen_ships[key]=true
    if engine.operational(ship) and engine.is_ship(ship) then
     local sector=engine.sector(ship)
     if sector then
      local skey=engine.key(sector)
      if skey~='' and not selected_sector[skey] then
       local id=key:gsub('ULL$','');assert(id:match('^%d+$'))
       actors[#actors+1]=ConvertStringToLuaID(id);selected_sector[skey]=true
       if #actors==2 then return end
      end
     end
    end
   end
   coroutine.yield()
  end
 end
 error('fewer than two observed sectors')
end
function X4LAN_AUTHORITY_SECTOR_READY()
 if failed then error('sector experiment failed') end
 local now=GetCurRealTime();started=started or now
 if now-started>assert(cfg.authority_sector_deadline) then fail('deadline');error('sector deadline') end
 if not C.IsGamePaused() then
  if state~='new' then fail('pause_lost');error('sector experiment lost pause') end
  if not requested_pause then requested_pause=true;assert(type(Pause)=='function');Pause() end
  return false
 end
 guard()
 if state=='new' then
  if phase=='save' then scan=coroutine.create(select_existing);state='scan'
  else state='status';send(registry,'Status',{}) end
 elseif state=='scan' then
  local ok,err=coroutine.resume(scan)
  if not ok then fail('scan');error(err) end
  if coroutine.status(scan)=='dead' then
   if #actors~=2 then fail('selection');error('selection incomplete') end
   state='initialize';send(registry,'Initialize',{epoch=epoch})
  end
 end
 return state=='done'
end
function X4LAN_AUTHORITY_SECTOR_ENSURE_PAUSED()
 guard()
 if state~='done' then fail('not_verified');error('sector fixture not verified') end
end
