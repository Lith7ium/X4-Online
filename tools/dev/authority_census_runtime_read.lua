-- Paused, read-only source census. Local IDs are diagnostics, never network IDs.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_census_runtime_read~=true then return end
local ffi=require('ffi')
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
ffi.cdef[[bool IsGamePaused(void);bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);
bool IsComponentClass(UniverseID,const char*);UniverseID GetContextByClass(UniverseID,const char*,bool);
UIPosRot GetObjectPositionInSector(UniverseID);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
local C=ffi.C;local epoch,nonce=cfg.authority_census_epoch,cfg.authority_census_nonce
local limit=cfg.authority_census_limit
assert(type(epoch)=='string' and #epoch==32 and epoch:match('^[0-9a-f]+$'))
assert(type(nonce)=='string' and #nonce==32 and nonce:match('^[0-9a-f]+$'))
assert(type(limit)=='number' and limit==math.floor(limit) and limit>=1 and limit<=10054)
local index=1;local state='new';local failed=false;local pending;local started,last,game
local counts={ok=0,unavailable=0,no_sector=0,docked_or_stored=0,local_invalid=0};local actors,sectors={},{};local sector_count=0
local function log(s) DebugError('[X4LAN] AUTH_CENSUS_RUNTIME '..s) end
local function fail(s) if not failed then failed=true;state='failed';pending=nil;log('ERROR '..s) end end
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function guard()
 assert(not failed)
 local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_census_save_path)
 assert(C.IsGamePaused())
 local now=GetCurRealTime();local current=tonumber(C.GetCurrentGameTime())
 assert(finite(now) and now>=0 and (not last or now>=last) and finite(current) and current>=0)
 started=started or now;last=now;game=game or current
 assert(now-started<=cfg.authority_census_deadline and current==game)
 return now
end
local function valid(a,s)
 return C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship')
  and C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s
end
RegisterEvent('X4AuthorityCensusRuntimeRead.Refused',function() fail('registry_refused') end)
RegisterEvent('X4AuthorityCensusRuntimeRead.Result',function(_,row)
 if failed then return end
 local ok=pcall(function()
  local now=guard();assert(state=='wait' and pending and now<=pending.deadline)
  assert(type(row)=='string' and #row<=240)
  local id,ep,n,status,actor,sector=row:match('^([0-9a-f%-]+)|([0-9a-f]+)|([0-9]+)|([a-z_]+)|([^|]+)|([^|]+)$')
  assert(id==pending.id and ep==epoch and n==tostring(index))
  if status=='ok' then
   local a=X4LAN_RESOLVE_STRING.parse_hex(actor);local s=X4LAN_RESOLVE_STRING.parse_hex(sector)
   assert(a and s)
   local key=tostring(a);assert(not actors[key]);actors[key]=true
   if valid(a,s) then
    local p=C.GetObjectPositionInSector(a);guard()
    local x,y,z=tonumber(p.x),tonumber(p.y),tonumber(p.z)
    if finite(x) and finite(y) and finite(z) and valid(a,s) then
     local skey=tostring(s);if not sectors[skey] then sectors[skey]=true;sector_count=sector_count+1 end
     counts.ok=counts.ok+1
     log(('ROW index=%d status=ok local_sector=%s x=%.17g y=%.17g z=%.17g'):format(index,sector,x,y,z))
    else counts.local_invalid=counts.local_invalid+1;log('ROW index='..index..' status=local_invalid') end
   else counts.local_invalid=counts.local_invalid+1;log('ROW index='..index..' status=local_invalid') end
  elseif status=='unavailable' or status=='no_sector' or status=='docked_or_stored' then
   assert(actor=='0' and sector=='0');counts[status]=counts[status]+1
   log('ROW index='..index..' status='..status)
  else error('invalid or faulted registry response') end
  pending=nil;index=index+1;state='next'
 end)
 if not ok then fail('response') end
end)
function X4LAN_CENSUS_RUNTIME_READY()
 if failed then error('census runtime read failed') end
 local ok=pcall(function()
  local now=guard()
  if pending then assert(now<=pending.deadline) end
  if state=='new' or state=='next' then
   if index>limit then
    state='done'
    log(('DONE requested=%d ok=%d unavailable=%d no_sector=%d docked_or_stored=%d local_invalid=%d sectors=%d game=%.17g'):format(
     limit,counts.ok,counts.unavailable,counts.no_sector,counts.docked_or_stored,counts.local_invalid,sector_count,game))
   else
    local id=nonce..'-'..tostring(index);pending={id=id,deadline=now+10};state='wait'
    local sent=AddUITriggeredEvent('X4AuthorityCensusRuntimeRead','Read',{epoch=epoch,index=index,request_id=id})
    assert(sent~=false)
   end
  elseif state~='wait' and state~='done' then error('invalid census state') end
 end)
 if not ok then fail('state');error('census runtime read failed') end
 return state=='done'
end
