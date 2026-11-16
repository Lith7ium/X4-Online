-- Opt-in paused two-process frame probe. No writes; handles stay local.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_frame_enabled~=true then return end
local ffi=require('ffi')
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;') end
ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);UIPosRot GetObjectPositionInSector(UniverseID);
 const char* GetObjectIDCode(UniverseID);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
local C=ffi.C
local epoch,nonce,index,sector=cfg.authority_frame_epoch,cfg.authority_frame_nonce,cfg.authority_frame_ship_index,cfg.authority_frame_sector
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$') end
assert(token(epoch) and token(nonce) and epoch~=nonce and index==1318 and sector=='cluster_115_sector001_macro')
local wanted={['AAJ-808']=true,['UKN-243']=true,['RZT-476']=true,['LMC-637']=true,['OKE-308']=true,
 ['UJU-480']=true,['LOO-275']=true,['SJE-557']=true,['ODV-102']=true,['UTM-602']=true,['SUM-216']=true}
local allowed_macro='station_gen_factory_base_01_macro';local allowed_owner='pioneers'
local state,busy,failed='new',false,false
local last,deadline,game,local_sector,ship_seen,station_count,chosen=nil,nil,nil,nil,false,0,0
local actors,codes={},{}
local function log(s)DebugError('[X4LAN] AUTH_FRAME_READ '..s)end
local function fail(reason)if not failed then failed=true;state='failed';log('ERROR '..nonce..' '..reason)end;return false end
local function finite(x)return type(x)=='number' and x==x and x~=-math.huge and x~=math.huge end
local function guard()
 if failed then return false end
 local p=C.GetSaveFolderPath()
 if p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=cfg.authority_load_save_path or
    not C.IsPlayerValid() or not C.IsGamePaused() or type(X4LAN_AUTHORITY_MARKER_READY)~='function' or
    X4LAN_AUTHORITY_MARKER_READY()~=true then return false end
 local now,t=GetCurRealTime(),tonumber(C.GetCurrentGameTime())
 if not finite(now) or now<0 or (last and now<last) or (deadline and now>=deadline) or not finite(t) or t<0 then return false end
 if game and t~=game then return false end
 last=now;game=game or t
 return C.IsPlayerValid() and C.IsGamePaused()
end
local function key(v)local n=X4LAN_RESOLVE_STRING.actor_u64(v);return n and tostring(n):gsub('ULL$','') or nil end
local function local_ref(v)
 local expected=key(v);assert(expected and expected:match('^[1-9]%d*$'))
 local ref=ConvertStringToLuaID(expected);local kind=type(ref)
 if kind=='number' or kind=='cdata' then assert(key(ref)==expected) else assert(kind=='userdata') end
 assert(key(ConvertIDTo64Bit(ref))==expected)
 return ref,expected
end
local function live(a,s,kind)
 return C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,kind) and
  C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s
end
local function read(value)
 assert(guard() and state=='waiting' and type(value)=='string' and #value<=768)
 local id,kind,ah,sh,code,macro,owner=value:match('^([0-9a-f]+)|([a-z]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([^|]+)|([^|]+)|([^|]+)$')
 assert(id==nonce and (kind=='ship' or kind=='station') and code:match('^[A-Z0-9]+%-[0-9]+$') and
  #code<=32 and macro:match('^[A-Za-z0-9_]+$') and owner:match('^[A-Za-z0-9_]+$'))
 assert((kind=='ship' and not ship_seen and station_count==0) or (kind=='station' and ship_seen and station_count<128))
 local a=X4LAN_RESOLVE_STRING.parse_hex(ah);local s=X4LAN_RESOLVE_STRING.parse_hex(sh);assert(a and s)
 local ref,ak=local_ref(a);local sk=assert(key(s));assert(not actors[ak] and not codes[code:lower()])
 assert(not local_sector or local_sector==sk);local_sector=sk
 assert(live(a,s,kind) and guard())
 local ptr=C.GetObjectIDCode(a);assert(ptr~=nil and ptr~=ffi.NULL and ffi.string(ptr)==code)
 local actual_macro,actual_owner=GetComponentData(ref,'macro','owner')
 assert(actual_macro==macro and actual_owner==owner and guard() and live(a,s,kind))
 local p=C.GetObjectPositionInSector(a);assert(guard() and live(a,s,kind))
 local q=C.GetObjectPositionInSector(a);assert(guard() and live(a,s,kind))
 local x,y,z=tonumber(p.x),tonumber(p.y),tonumber(p.z)
 assert(finite(x) and finite(y) and finite(z) and math.abs(x)<=1e9 and math.abs(y)<=1e9 and math.abs(z)<=1e9 and
  x==tonumber(q.x) and y==tonumber(q.y) and z==tonumber(q.z))
 ptr=C.GetObjectIDCode(a);assert(ptr~=nil and ptr~=ffi.NULL and ffi.string(ptr)==code)
 local m2,o2=GetComponentData(ref,'macro','owner');assert(m2==macro and o2==owner and guard() and live(a,s,kind))
 actors[ak]=true;codes[code:lower()]=true
 if kind=='ship' then ship_seen=true else station_count=station_count+1 end
 if kind=='ship' or wanted[code] then
  if kind=='station' then assert(macro==allowed_macro and owner==allowed_owner);chosen=chosen+1 end
  log(('ROW %s %s %s %s %s %s %.17g %.17g %.17g %.17g'):format(nonce,kind,code,macro,owner,sector,game,x,y,z))
 end
end
assert(RegisterEvent('X4AuthorityFrameRead.Result',function(_,value)
 if failed then return end
 if busy then fail('reentrant');return end
 busy=true;local ok=pcall(read,value);busy=false;if not ok then fail('row') end
end)~=false)
assert(RegisterEvent('X4AuthorityFrameRead.Done',function(_,value)
 if failed then return end
 if busy then fail('reentrant');return end
 busy=true;local ok=pcall(function()
  assert(guard() and state=='waiting' and type(value)=='string')
  local id,n=value:match('^([0-9a-f]+)|([0-9]+)$')
  assert(id==nonce and n==tostring(station_count) and ship_seen and chosen>=3)
  state='done';deadline=nil;log(('DONE %s %d %.17g'):format(nonce,chosen,game))
 end);busy=false;if not ok then fail('done') end
end)~=false)
assert(RegisterEvent('X4AuthorityFrameRead.Refused',function()fail('refused')end)~=false)
function X4LAN_FRAME_READ_TICK()
 if failed then return end
 if busy then fail('reentrant');return end
 busy=true;local ok=pcall(function()
  assert(guard())
  if state=='new' then
   state='waiting';deadline=last+30
   assert(AddUITriggeredEvent('X4AuthorityFrameRead','Read',{request_id=nonce,epoch=epoch,index=index})~=false)
   assert(state=='waiting' and guard())
  else assert(state=='waiting' or state=='done')end
 end);busy=false;if not ok then fail('tick') end
end
