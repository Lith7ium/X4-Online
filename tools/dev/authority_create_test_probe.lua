-- Disposable two-process test only. No multiplayer admission or durable guarantee.
local cfg=X4LAN_CONFIG
if not cfg or not cfg.authority_create_role then return end
local ffi=require('ffi');ffi.cdef[[bool IsPlayerValid(void); bool IsGamePaused(void);]]
local role=cfg.authority_create_role
assert(role=='server' or role=='client')
local epoch=assert(cfg.authority_create_epoch)
local reg='X4AuthorityShipRegistry';local receiver='X4AuthorityShipCreateReceiver';local fixture='X4AuthorityCreateFixture'
local phase=role=='server' and 'init' or 'idle';local ready=false;local failed=false;local net;local next_hello=0
local fields={};local seen={};local actor;local baseline;local mode;local sector_id
local motion, motion_net, motion_finished
local function log(s) DebugError('[X4LAN] AUTH_CREATE '..role..' '..s) end
local function fail(s)
 if not failed then
  failed=true
  if motion then pcall(function() motion:stop() end);motion=nil;motion_finished=true end
  if motion_net then pcall(function() motion_net:close() end);motion_net=nil end
  log('ERROR '..s)
 end
end
local function send(name,args) AddUITriggeredEvent(name[1],name[2],args or {}) end
local function key(v) local n=ConvertIDTo64Bit(v);assert(n and n~=0);return (tostring(n):gsub('ULL$','')) end
local function emit(s) assert(net and net:send('RESULT|'..cfg.authority_create_lease..'|'..role..'|'..s)) end
local function count()
 assert(ffi.C.IsGamePaused())
 local e=assert(X4LAN_AUTHORITY_SHIP_ENGINE).new();local n=e.fleet_count('argon')
 assert(n>=0 and n<200000);local rows,cut=e.fleet('argon',n+1)
 assert(not cut and #rows==n and e.fleet_count('argon')==n)
 local total=0
 for _,s in ipairs(rows) do
  if e.operational(s) and e.is_ship(s) then
   local id=(e.key(s):gsub('ULL$',''))
   local m=GetComponentData(ConvertStringToLuaID(id),'macro')
   assert(type(m)=='string' and m:match('^[%w_]+$'), 'invalid fleet macro')
   if m=='ship_arg_s_fighter_01_a_macro' then total=total+1 end
  end
 end
 return total
end
local function request_create(conflict)
 local args={epoch=epoch,index=1,macro=fields.Macro,sector=fields.Sector,owner=fields.Owner,
  seed=fields.Seed,x=fields.X,y=fields.Y,z=fields.Z}
 if conflict then args.seed=fields.Seed+1 end
 send({receiver,'Create'},args)
end
RegisterEvent(reg..'.Initialized',function(_,v)
 if phase~='init_reg' or v~=epoch then fail('init_reg');return end
 phase='init_receiver';send({receiver,'Initialize'},{epoch=epoch})
end)
RegisterEvent(receiver..'.Initialized',function(_,v)
 if phase~='init_receiver' or v~=epoch then fail('init_receiver');return end
 phase='idle';ready=true;log('INITIALIZED')
end)
RegisterEvent(fixture..'.Ship',function(_,v)
 if phase~='spawn' or actor then fail('spawn_actor');return end
 actor=v
end)
RegisterEvent(fixture..'.SectorId',function(_,v)
 if (phase~='spawn' and phase~='descriptor') or type(v)~='string' or not v:match('^[%w_]+$') then fail('sector_id');return end
 sector_id=v
end)
RegisterEvent(fixture..'.Spawned',function(_,v)
 if phase~='spawn' or not actor or not sector_id then fail('spawn');return end
 for _,name in ipairs({'Macro','Owner','Seed','X','Y','Z'}) do if not seen[name] then fail('missing_'..name);return end end
 if fields.Macro~='ship_arg_s_fighter_01_a_macro' or fields.Owner~='argon' or fields.Seed~=7183 or fields.X~=-400 or fields.Y~=100000 or fields.Z~=500 then fail('spawn_descriptor');return end
 local id=key(actor)
 phase='enroll';send({reg,'Enroll'},{epoch=epoch,ship=ConvertStringToLuaID(id)})
end)
RegisterEvent(reg..'.Enrolled',function(_,v)
 if phase~='enroll' or tonumber(v)~=1 then fail('enroll');return end
 local c=count();if c~=baseline+1 then fail('server_count');return end
 phase='idle';emit('SPAWN|1|'..key(actor)..'|'..baseline..'|'..c..'|'..sector_id..'|'..fields.Macro..'|'..fields.Owner..'|'..fields.Seed..'|'..fields.X..'|'..fields.Y..'|'..fields.Z);log('SPAWN id='..key(actor)..' baseline='..baseline..' count='..c)
end)
for _,name in ipairs({'Macro','Owner','Seed','X','Y','Z'}) do
 RegisterEvent(fixture..'.'..name,function(_,v)
  if phase~='spawn' or seen[name] or v==nil then fail('descriptor_'..name);return end
  seen[name]=true;fields[name]=v
 end)
end
RegisterEvent(fixture..'.Described',function()
 if phase~='descriptor' or not sector_id or sector_id~=fields.Sector then fail('descriptor_sector');return end
 phase='creating';request_create(false)
end)
RegisterEvent(receiver..'.Created',function(_,v)
 if phase~='creating' or tonumber(v)~=1 then fail('created');return end
 phase='resolve';send({reg,'Resolve'},{epoch=epoch,index=1})
end)
RegisterEvent(reg..'.Actor',function(_,v)
 if phase~='resolve' then fail('resolve');return end
 local id=key(v);local c=count()
 if mode=='create' then
  if c~=baseline+1 then fail('first_count');return end
  actor=v
 elseif mode=='replay' then
  if id~=key(actor) or c~=baseline+1 then fail('replay_count_or_actor');return end
 else fail('resolve_mode');return end
 phase='inspect';send({fixture,'Inspect'},{epoch=epoch,index=1})
end)
local inspect={}
for _,name in ipairs({'RegistryShip','Reverse','Receipt'}) do
 RegisterEvent(fixture..'.'..name,function(_,v) if phase~='inspect' or inspect[name] then fail('inspect_'..name);return end;inspect[name]=v end)
end
RegisterEvent(fixture..'.Inspected',function(_,v)
 if phase~='inspect' or tonumber(v)~=1 or not inspect.RegistryShip or not inspect.Receipt or tonumber(inspect.Reverse)~=1 or key(inspect.RegistryShip)~=key(actor) or key(inspect.Receipt)~=key(actor) then fail('inspect');return end
 inspect={};local id=key(actor);local c=count();phase='idle';emit(string.upper(mode)..'|1|'..id..'|'..baseline..'|'..c..'|'..sector_id);log(string.upper(mode)..' id='..id..' baseline='..baseline..' count='..c)
end)
for _,name in ipairs({'SpawnFailed','DescribeFailed','InspectFailed'}) do RegisterEvent(fixture..'.'..name,function() fail(name) end) end
RegisterEvent(receiver..'.Refused',function()
 if phase~='conflict' and phase~='after_conflict' then fail('unexpected_refusal');return end
 local c=count();if c~=baseline+1 then fail('refusal_count');return end
 local was=phase;phase='idle';emit(string.upper(was)..'|'..c);log(string.upper(was)..' count='..c)
end)
RegisterEvent(reg..'.Faulted',function() if phase~='status_fault' then fail('unexpected_fault');return end;phase='idle';emit('FAULTED') end)
for _,name in ipairs({'Refused','Unavailable','Uninitialized'}) do
 RegisterEvent(reg..'.'..name,function() fail('registry_'..name) end)
end
if cfg.authority_motion_test==true then
 RegisterEvent('X4AuthorityRegistryMotionGuard.Verified',function(_,value)
  if failed then return end
  if motion_finished and not motion then return end -- late response to the stopped request
  if not motion then fail('unexpected_motion_guard');return end
  local ok=pcall(function() motion:verified(value) end)
  if not ok then fail('motion_guard') end
 end)
 RegisterEvent('X4AuthorityRegistryMotionGuard.Refused',function()
  if failed then return end
  if motion_finished and not motion then return end
  if motion then pcall(function() motion:refused() end) end
  fail('motion_guard_refused')
 end)
end
function X4LAN_AUTHORITY_CREATE_READY()
 if failed then error('creation test failed') end
 if not ffi.C.IsGamePaused() then Pause();return false end
 if phase=='init' then phase='init_reg';send({reg,'Initialize'},{epoch=epoch}) end
 return ready
end
local function frame()
 if failed or not ffi.C.IsPlayerValid() then return end
 if motion then motion:tick() end
 if not net then
  local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
  net=lib.open('127.0.0.1',cfg.authority_create_port)
 end
 local now=GetCurRealTime()
 if now>=next_hello then emit('HELLO');next_hello=now+.25 end
 for _=1,4 do
  local packet=net:receive();if not packet then break end
  local lease,op,tail=packet:match('^CMD|([0-9a-f]+)|([A-Z]+)(.*)$')
  assert(lease==cfg.authority_create_lease and phase=='idle' and ffi.C.IsGamePaused())
  assert(not motion or op=='MOTIONSTOP', 'motion test is active')
  if op=='SPAWN' and role=='server' then
   assert(tail=='');baseline=count();phase='spawn';fields={};seen={};send({fixture,'Spawn'})
  elseif op=='CREATE' and role=='client' and not mode then
   local macro,sector,owner,seed,x,y,z=tail:match('^|([%w_]+)|([%w_]+)|([%w_]+)|(%d+)|(-?%d+)|(-?%d+)|(-?%d+)$')
   assert(macro=='ship_arg_s_fighter_01_a_macro' and owner=='argon' and sector and tonumber(seed)==7183 and tonumber(x)==-400 and tonumber(y)==100000 and tonumber(z)==500)
   fields={Macro=macro,Sector=sector,Owner=owner,Seed=tonumber(seed),X=tonumber(x),Y=tonumber(y),Z=tonumber(z)}
   baseline=count();mode='create';sector_id=nil;phase='descriptor';send({fixture,'Descriptor'})
  elseif op=='REPLAY' and role=='client' and mode=='create' then
   assert(tail=='');mode='replay';phase='creating';request_create(false)
  elseif op=='CONFLICT' and role=='client' and mode=='replay' then
   assert(tail=='');phase='conflict';request_create(true)
  elseif op=='STATUS' and role=='client' and mode=='replay' then
   assert(tail=='');phase='status_fault';send({reg,'Status'},{})
  elseif op=='AFTER' and role=='client' and mode=='replay' then
   assert(tail=='');phase='after_conflict';request_create(false)
  elseif op=='MOTION' and cfg.authority_motion_test==true and actor and sector_id and not motion and not motion_finished then
   assert(tail=='')
   local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
   motion_net=lib.open('127.0.0.1',cfg.authority_motion_port)
   motion=assert(X4LAN_AUTHORITY_REGISTRY_MOTION_NATIVE).new({enabled=true,role=role=='server' and 'SOURCE' or 'GUEST',
    actor=ffi.new('UniverseID',ConvertIDTo64Bit(actor)),epoch=epoch,index=1,frame=sector_id,
    expected_path=cfg.authority_motion_save_path,transport=motion_net,lease=cfg.authority_motion_lease,
    probe_module=assert(X4LAN_AUTHORITY_REGISTRY_MOTION),wire_module=assert(X4LAN_AUTHORITY_FIXTURE_WIRE),
    continuous_module=assert(X4LAN_AUTHORITY_FIXTURE_CONTINUOUS),clock=assert(lib.monotonic),log=log,
    test_nudge=role=='server'})
   emit('MOTION');log('MOTION_START')
  elseif op=='MOTIONSTOP' and cfg.authority_motion_test==true and motion then
   assert(tail=='');motion:stop();motion=nil;motion_finished=true;motion_net:close();motion_net=nil;emit('MOTIONSTOP');log('MOTION_STOP')
  else error('bad command') end
 end
end
SetScript('onUpdate',function() local ok,err=pcall(frame);if not ok then fail(tostring(err)) end end)
