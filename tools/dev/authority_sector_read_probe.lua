-- Disposable paused read probe; the existing load callback owns all updates.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_sector_read~=true then return end
local ffi=require('ffi')
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
ffi.cdef[[bool IsGamePaused(void);bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);
 bool IsComponentClass(UniverseID,const char*);UniverseID GetContextByClass(UniverseID,const char*,bool);
 UIPosRot GetObjectPositionInSector(UniverseID);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
local C=ffi.C;local epoch=assert(cfg.authority_sector_epoch);local slot=assert(cfg.authority_sector_slot)
assert(type(epoch)=='string' and #epoch==32 and epoch:match('^[0-9a-f]+$'))
assert(slot==1 or slot==2)
local state='new';local failed=false;local start,last_time;local current={};local first;local sample
local fields={'Pilot','OrderId','OrderState','Actor','Sector','Verified'}
local function log(s) DebugError('[X4LAN] AUTH_SECTOR_READ '..s) end
local function fail(s) if not failed then failed=true;state='failed';log('ERROR '..s) end end
local function number(v) return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function guard()
 if failed then error('read failed') end
 local p=C.GetSaveFolderPath()
 if p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=cfg.authority_read_save_path then
  fail('profile');error('invalid profile')
 end
 if not C.IsGamePaused() then fail('pause_lost');error('pause lost') end
 local now=GetCurRealTime()
 if not number(now) or now<0 or (last_time and now<last_time) then fail('clock');error('invalid clock') end
 last_time=now;start=start or now
 if now-start>30 then fail('deadline');error('read deadline') end
end
local function issue(screen,op,args)
 guard();local sent=AddUITriggeredEvent(screen,op,args)
 if sent==false then fail('dispatch');error('dispatch refused') end
end
local function localid(value)
 -- The original MD handle itself must be a safe integer or exact uint64.
 -- Once a rounded double has been converted to cdata, lost bits are invisible.
 local original=X4LAN_RESOLVE_STRING.actor_u64(value)
 if not original then return nil end
 local ok,id=pcall(ConvertIDTo64Bit,value)
 if not ok then return nil end
 id=X4LAN_RESOLVE_STRING.actor_u64(id)
 if not id or id~=original then return nil end
 return id
end
local function snapshot(actor,sector)
 guard()
 assert(C.IsValidComponent(actor) and C.IsComponentOperational(actor) and C.IsComponentClass(actor,'ship'))
 assert(C.GetContextByClass(actor,'sector',false)==sector)
 local g1=tonumber(C.GetCurrentGameTime());local pos=C.GetObjectPositionInSector(actor);local g2=tonumber(C.GetCurrentGameTime())
 guard()
 assert(C.IsValidComponent(actor) and C.IsComponentOperational(actor) and C.IsComponentClass(actor,'ship'))
 assert(C.GetContextByClass(actor,'sector',false)==sector)
 local x,y,z=tonumber(pos.x),tonumber(pos.y),tonumber(pos.z)
 assert(number(g1) and g1>=0 and g1==g2 and number(x) and number(y) and number(z))
 return {game=g1,x=x,y=y,z=z}
end
local function start_read(next_state)
 state=next_state;current={};issue('X4AuthoritySectorReadGuard','Read',{epoch=epoch,slot=slot})
end
RegisterEvent('X4AuthoritySectorReferenceFixture.Verified',function(_,value)
 if failed then return end
 guard();if state~='fixture' or value~=epoch then fail('fixture');return end
 start_read('first')
end)
RegisterEvent('X4AuthoritySectorReferenceFixture.Refused',function() if not failed then fail('fixture_refused') end end)
for _,name in ipairs(fields) do
 RegisterEvent('X4AuthoritySectorReadGuard.'..name,function(_,value)
  if failed then return end
  guard()
  if (state~='first' and state~='second') or fields[#current+1]~=name then fail('event_order');return end
  if name=='Pilot' and value~='present' and value~='absent' then fail('pilot');return end
  if name=='OrderId' and (type(value)~='string' or #value<1 or #value>96 or not value:match('^[%w_%-]+$')) then fail('order');return end
  if name=='OrderState' and value~='started' and value~='critical' and value~='other' and value~='none' then fail('order_state');return end
  if name=='Actor' or name=='Sector' then value=localid(value);if not value then fail('local_id');return end end
  if name=='Verified' and value~=epoch then fail('epoch');return end
  current[#current+1]=value
  if name=='Verified' then
   if (current[2]=='none')~=(current[3]=='none') then fail('order_consistency');return end
   if state=='first' then
    first=current
    local ok,result=pcall(snapshot,first[4],first[5])
    if not ok then fail('sample');return end
    sample=result;start_read('second')
   else
    for i=1,5 do if current[i]~=first[i] then fail('changed');return end end
    local ok,result=pcall(snapshot,current[4],current[5])
    if not ok or result.game~=sample.game or result.x~=sample.x or result.y~=sample.y or result.z~=sample.z then fail('readback');return end
    state='done'
    log(('DONE slot=%d pilot=%s order=%s state=%s game=%.17g x=%.17g y=%.17g z=%.17g'):format(slot,first[1],first[2],first[3],sample.game,sample.x,sample.y,sample.z))
   end
  end
 end)
end
RegisterEvent('X4AuthoritySectorReadGuard.Refused',function() if not failed then fail('refused') end end)
function X4LAN_SECTOR_READ_READY()
 if failed then error('sector read failed') end
 guard()
 if state=='new' then state='fixture';issue('X4AuthoritySectorReferenceFixture','Verify',{epoch=epoch}) end
 return state=='done'
end
function X4LAN_SECTOR_READ_STARTED() return state~='new' end
