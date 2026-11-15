-- Default-off isolated server diagnostic. This module NEVER calls a setter,
-- creates ships, resumes/pauses X4, or controls the WorldCoordinator.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_npc_flight_source~=true then return end
local ffi=require('ffi')
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
ffi.cdef[[
 const char* GetSaveFolderPath(void); bool IsGamePaused(void); bool IsPlayerValid(void);
 bool IsValidComponent(UniverseID); bool IsComponentOperational(UniverseID);
 bool IsComponentClass(UniverseID,const char*); UniverseID GetContextByClass(UniverseID,const char*,bool);
 UniverseID GetPlayerControlledShipID(void); UniverseID GetPlayerOccupiedShipID(void);
 UniverseID GetPlayerContainerID(void); UIPosRot GetObjectPositionInSector(UniverseID);
 double GetCurrentGameTime(void);
]]
local C=ffi.C
local epoch=assert(cfg.authority_create_epoch);local lease=assert(cfg.authority_npc_lease)
local phase,failed='idle',false
local net,wire,wire_net,clock,actor,sector_key,zone_key,frame,pending,previous
local ready_fields={};local hello_at=0;local armed_at;local last_game
local function key(v) return v and v~=0 and (tostring(v):gsub('ULL$','')) or '' end
local function log(s) DebugError('[X4LAN] AUTH_NPC_SOURCE '..s) end
local function fail(s)
 if not failed then failed=true;phase='failed';pending=false
  if wire_net then pcall(function() wire_net:close() end);wire_net=nil end
  log('ERROR '..s)
 end
end
local function emit(s) assert(net and net:send('NPCRESULT|'..lease..'|'..s)) end
local function profile()
 local p=C.GetSaveFolderPath()
 return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_motion_save_path
end
local function valid_clock(n) return type(n)=='number' and n==n and n>=0 and n~=math.huge end
local function guard()
 assert(phase=='running' and not C.IsGamePaused() and profile() and actor and C.IsValidComponent(actor) and C.IsComponentOperational(actor) and C.IsComponentClass(actor,'ship'))
 local sector=C.GetContextByClass(actor,'sector',false);local zone=C.GetContextByClass(actor,'zone',false)
 local sk,zk=key(sector),key(zone);assert(sk~='' and zk~='')
 if sector_key then assert(sector_key==sk and zone_key==zk) else sector_key,zone_key=sk,zk end
 local controlled,occupied,container=C.GetPlayerControlledShipID(),C.GetPlayerOccupiedShipID(),C.GetPlayerContainerID()
 for _,v in ipairs({controlled,occupied,container}) do assert(key(v)~=key(actor)) end
 assert(key(container)~='' and C.IsValidComponent(container))
 local ship=C.GetContextByClass(container,'ship',true)
 if key(ship)~='' then assert(key(ship)~=key(actor))
 else assert(key(C.GetContextByClass(container,'station',true))~='') end
 local docked,docking,stored=GetComponentData(ConvertStringToLuaID(key(actor)),'isdocked','isdocking','isinternallystored')
 assert(docked==false and docking==false and stored==false)
 return sector
end
local function position()
 guard();local p=C.GetObjectPositionInSector(actor)
 local result={x=tonumber(p.x),y=tonumber(p.y),z=tonumber(p.z)}
 for _,n in pairs(result) do assert(type(n)=='number' and n==n and math.abs(n)<math.huge) end
 guard();return result
end
local function sample()
 local p=position();local now=clock();local game=tonumber(C.GetCurrentGameTime())
 assert(valid_clock(now) and valid_clock(game) and (not last_game or game>=last_game));last_game=game
 local reference=previous
 if reference then
  local dt=now-reference.t;assert(dt>=0)
  if dt>=.02 and dt<=1 then
   p.vx,p.vy,p.vz=(p.x-reference.x)/dt,(p.y-reference.y)/dt,(p.z-reference.z)/dt
   assert(math.abs(p.vx)<math.huge and math.abs(p.vy)<math.huge and math.abs(p.vz)<math.huge)
   if math.sqrt(p.vx*p.vx+p.vy*p.vy+p.vz*p.vz)>5000 then p.vx,p.vy,p.vz=nil,nil,nil end
  end
  if dt>=.02 then previous={x=p.x,y=p.y,z=p.z,t=now} end
 else previous={x=p.x,y=p.y,z=p.z,t=now} end
 local before=wire.sent;wire:step(p)
 if wire.sent>before and p.vx then
  log(('SAMPLE epoch=%s index=1 frame=%s seq=%.0f real_time=%.17g game_time=%.17g x=%.17g y=%.17g z=%.17g vx=%.17g vy=%.17g vz=%.17g reference_real_time=%.17g reference_x=%.17g reference_y=%.17g reference_z=%.17g'):format(epoch,frame,wire.sent,now,game,p.x,p.y,p.z,p.vx,p.vy,p.vz,reference.t,reference.x,reference.y,reference.z))
 end
end
for _,name in ipairs({'Pilot','OrderId','GameTime'}) do
 RegisterEvent('X4AuthorityNPCFlightFixture.'..name,function(_,v)
  if phase~='ordering' or ready_fields[name]~=nil or v==nil then fail('order_'..name);return end
  ready_fields[name]=v
 end)
end
RegisterEvent('X4AuthorityNPCFlightFixture.Ready',function(_,v)
 local ok,err=pcall(function()
  assert(phase=='ordering' and ready_fields.Pilot~=nil and ready_fields.OrderId=='MoveWait' and ready_fields.GameTime~=nil)
  local reported=tonumber(ready_fields.GameTime);assert(valid_clock(reported))
  actor=ffi.new('UniverseID',ConvertIDTo64Bit(v));assert(key(actor)~='')
  local now=clock();local game=tonumber(C.GetCurrentGameTime());assert(valid_clock(now) and valid_clock(game))
  phase='armed'
  log(('ORDER epoch=%s index=1 frame=%s pilot=present order=MoveWait real_time=%.17g game_time=%.17g'):format(epoch,frame,now,game))
  emit('ARMED|'..frame)
  armed_at=now+.25
 end)
 if not ok then fail('order_ready') end
end)
RegisterEvent('X4AuthorityNPCFlightFixture.Refused',function() fail('order_refused') end)
RegisterEvent('X4AuthorityNPCFlightGuard.Verified',function(_,v)
 if phase=='stopped' or failed then return end
 local ok=pcall(function()
  assert(phase=='running' and pending and key(ffi.new('UniverseID',ConvertIDTo64Bit(v)))==key(actor))
  pending=false;sample()
 end)
 if not ok then fail('guard_or_sample') end
end)
RegisterEvent('X4AuthorityNPCFlightGuard.Refused',function() if phase~='stopped' then fail('guard_refused') end end)
local function update()
 if failed or not C.IsPlayerValid() then return end
 if not net then
  assert(profile() and cfg.test_profile=='45841')
  local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
  clock=assert(lib.monotonic);net=lib.open('127.0.0.1',cfg.authority_npc_port)
 end
 local now=clock();assert(valid_clock(now))
 if now>=hello_at then emit('HELLO');hello_at=now+.25 end
 for _=1,4 do
  local packet=net:receive();if not packet then break end
  local token,op,arg=packet:match('^NPCCMD|([0-9a-f]+)|([A-Z]+)|([%w_.%-]*)$')
  assert(token==lease)
  if op=='ARM' then
   assert(phase=='idle' and C.IsGamePaused() and arg~='' and #arg<=64)
   frame=arg;phase='ordering';ready_fields={}
   AddUITriggeredEvent('X4AuthorityNPCFlightFixture','Order',{epoch=epoch,index=1,frame=frame})
  elseif op=='STOP' then
   assert(phase=='running' and arg=='' and not C.IsGamePaused());phase='stopped';pending=false
   if wire_net then wire_net:close();wire_net=nil end
   emit('STOPPED')
  else error('unexpected NPC command') end
 end
 -- UDP send success does not establish delivery. Repeat only while the
 -- source is still paused and armed; never recreate the ship or order.
 if phase=='armed' and C.IsGamePaused() and armed_at and now>=armed_at then
  emit('ARMED|'..frame);armed_at=now+.25
 end
 if phase=='armed' and not C.IsGamePaused() then
  local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
  wire_net=lib.open('127.0.0.1',cfg.authority_motion_port)
  wire=assert(X4LAN_AUTHORITY_FIXTURE_WIRE).new(wire_net,'SOURCE',cfg.authority_motion_lease,epoch..'.1.'..frame,true)
  phase='running';emit('RUNNING')
 end
 if phase=='running' then
  assert(not C.IsGamePaused())
  if not pending then pending=true;AddUITriggeredEvent('X4AuthorityNPCFlightGuard','Validate',{epoch=epoch,index=1,frame=frame}) end
 end
end
SetScript('onUpdate',function() local ok=pcall(update);if not ok then fail('update') end end)
