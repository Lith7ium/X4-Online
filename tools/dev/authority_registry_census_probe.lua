-- Disposable registry diagnostic. This is not a multiplayer adapter.
local cfg=X4LAN_CONFIG
if not cfg or not cfg.authority_registry_phase then return end
local ffi=require('ffi');ffi.cdef[[bool IsGamePaused(void);]]
local phase=cfg.authority_registry_phase
assert(phase=='save' or phase=='load')
local max=assert(cfg.authority_registry_limit)
assert(type(max)=='number' and max>=1 and max<=200000 and max==math.floor(max))
local screen='X4AuthorityShipRegistry'
local state='new';local pending;local epoch;local count;local candidates={};local index=1
local known={};local sector_seen={};local sectors=0;local started;local failed=false
local enumerated,distinct,eligible,unconfirmed,unlocated=0,0,0,0,0
local inventory_task;local pause_requested=false;local pause_confirmed=false
local function log(s) DebugError('[X4LAN] AUTH_REGISTRY '..phase..' '..s) end
local function fail(s) if not failed then failed=true;state='failed';log('ERROR '..s) end end
local function send(op,args) AddUITriggeredEvent(screen,op,args) end
local function decimal(v)
 local n=ConvertIDTo64Bit(v)
 if not n or n==0 then return nil end
 return tostring(n):gsub('ULL$','')
end
local function enqueue_resolve()
 pending=index;state='resolving';send('Resolve',{epoch=epoch,index=index})
end
local function enqueue_enroll(id,kind)
 pending=index;state=kind;send('Enroll',{epoch=epoch,ship=ConvertStringToLuaID(id)})
end
RegisterEvent(screen..'.Initialized',function(_,v)
 if state~='initializing' or v~=epoch then fail('initialize');return end
 log('EPOCH '..v);state='enrolling'
end)
RegisterEvent(screen..'.Epoch',function(_,v)
 if state~='status' or epoch or type(v)~='string' or #v~=32 or not v:match('^[0-9a-f]+$') then fail('epoch');return end
 epoch=v;log('EPOCH '..v)
end)
RegisterEvent(screen..'.Count',function(_,v)
 local n=tonumber(v)
 if state~='status' or not epoch or not n or n~=math.floor(n) or n<1 or n>max then fail('count');return end
 count=n;state='resolve_next'
end)
RegisterEvent(screen..'.Enrolled',function(_,v)
 local n=tonumber(v)
 if not pending or n~=pending then fail('enroll_id');return end
 if state=='enroll_first' then
  state='enroll_repeat';send('Enroll',{epoch=epoch,ship=ConvertStringToLuaID(candidates[index])})
 elseif state=='enroll_repeat' then
  index=index+1;pending=nil;state='enrolling'
 elseif state=='reenroll' then
  index=index+1;pending=nil;state='resolve_next'
 else fail('enroll_order') end
end)
RegisterEvent(screen..'.Actor',function(_,v)
 if state~='resolving' or pending~=index then fail('resolve_order');return end
 local id=decimal(v)
 if not id or known[id] then fail('resolve_duplicate');return end
 if phase=='save' and id~=candidates[index] then fail('resolve_wrong_object');return end
 known[id]=true
 local macro=GetComponentData(ConvertStringToLuaID(id),'macro')
 if type(macro)~='string' or macro=='' or not macro:match('^[%w_]+$') then fail('macro');return end
 log('ROW '..index..' '..macro)
 enqueue_enroll(id,'reenroll')
end)
for _,event in ipairs({'Refused','Unavailable','Faulted','Uninitialized'}) do
 RegisterEvent(screen..'.'..event,function() fail('registry_'..event) end)
end
local function inventory()
 local engine=assert(X4LAN_AUTHORITY_SHIP_ENGINE).new()
 local factions,truncated=engine.factions(1024)
 assert(not truncated and #factions>0 and #factions<1024,'faction enumeration')
 local seen={}
 for _,faction in ipairs(factions) do
  local before=engine.fleet_count(faction)
  assert(before>=0 and before<=200000 and before==math.floor(before),'fleet count')
  local ships,cut=engine.fleet(faction,before+1)
  assert(not cut and #ships==before and engine.fleet_count(faction)==before,'fleet changed')
  for _,ship in ipairs(ships) do
   enumerated=enumerated+1
   if enumerated%256==0 then coroutine.yield() end
   local key=engine.key(ship)
   assert(key~='', 'invalid fleet member')
   if not seen[key] then
    seen[key]=true;distinct=distinct+1
    assert(distinct<=200000,'distinct object limit')
    if engine.operational(ship) and engine.is_ship(ship) then
     local sector=engine.sector(ship)
     if sector then
      eligible=eligible+1
      local skey=engine.key(sector)
      if skey~='' and not sector_seen[skey] then sector_seen[skey]=true;sectors=sectors+1 end
      if #candidates<max then
       local id=key:gsub('ULL$','')
       assert(id:match('^%d+$'),'invalid local object')
       candidates[#candidates+1]=id
      end
     else unlocated=unlocated+1 end
    else unconfirmed=unconfirmed+1 end
   end
  end
 end
 assert(#candidates>0,'no candidates')
 log('INVENTORY selected='..#candidates..' eligible='..eligible..' distinct='..distinct..
  ' enumerated='..enumerated..' unconfirmed='..unconfirmed..' unlocated='..unlocated..
  ' observed_sectors='..sectors..' truncated='..tostring(eligible>#candidates)..' coverage=unknown')
end
function X4LAN_AUTHORITY_REGISTRY_CENSUS_READY()
 if failed then error('registry census failed') end
 local now=GetCurRealTime();started=started or now
 if now-started>assert(cfg.authority_registry_deadline) then fail('deadline');error('registry census timed out') end
 if not ffi.C.IsGamePaused() then
  if pause_confirmed then fail('pause_lost');error('registry census lost pause') end
  if not pause_requested then pause_requested=true;assert(type(Pause)=='function');Pause() end
  return false
 end
 if not pause_confirmed then pause_confirmed=true;log('PAUSED') end
 if state=='new' then
  if phase=='save' then
   epoch=assert(cfg.authority_registry_epoch);assert(epoch:match('^[0-9a-f]+$') and #epoch==32)
   inventory_task=coroutine.create(inventory);state='inventory'
  else
   assert(cfg.authority_registry_epoch==nil);state='status';send('Status',{})
  end
 elseif state=='inventory' then
  local ok,err=coroutine.resume(inventory_task)
  if not ok then fail('inventory');error(err) end
  if coroutine.status(inventory_task)=='dead' then
   inventory_task=nil;state='initializing';send('Initialize',{epoch=epoch})
  end
 elseif state=='enrolling' then
  if index>#candidates then
   count=#candidates;index=1;state='resolve_next'
  else enqueue_enroll(candidates[index],'enroll_first') end
 elseif state=='resolve_next' then
  if index>count then state='done';log('DONE count='..count..' coverage=unknown independent_identity=false')
  else enqueue_resolve() end
 end
 return state=='done'
end
