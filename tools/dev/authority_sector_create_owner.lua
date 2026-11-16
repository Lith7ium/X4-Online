-- Default-off owner for a disposable sector-create experiment. No callbacks or
-- updates on import. The caller owns the sole X4 onUpdate and process fence.
local M={}
local names={'X4AuthoritySectorCreateInspect.Preflight','X4AuthoritySectorCreateInspect.Result',
 'X4AuthoritySectorCreateInspect.Refused','X4AuthorityShipCreateReceiver.Initialized',
 'X4AuthorityShipCreateReceiver.Created','X4AuthorityShipCreateReceiver.Refused'}
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(o.exclusive_events==true and type(o.register)=='function' and type(o.driver_factory)=='function')
 assert(o.diagnostic==nil or type(o.diagnostic)=='function')
 local state='new';local driver;local stage='new'
 local function fail()
  if state~='failed' and o.diagnostic then pcall(o.diagnostic,'OWNER_FAIL '..stage) end
  state='failed';return false
 end
 local owner={}
 function owner:start()
  if state~='new' then return fail() end
  state='registering'
  local ok=pcall(function()
   stage='driver_factory';driver=assert(o.driver_factory())
   stage='registration'
   for _,name in ipairs(names) do
    local registered=o.register(name,function(_,value)
     if state~='active' and state~='pending_fence' then fail();return end
     stage='callback'
     local good,accepted=pcall(driver.event,driver,name,value)
     if not good or accepted~=true or state=='failed' then fail();return end
     local state_ok,driver_state=pcall(driver.state,driver)
     if not state_ok then fail();return end
     if driver_state=='done' then state='pending_fence' end
    end)
    assert(registered~=false and state=='registering','event registration failed')
   end
   assert(state=='registering');state='active';stage='driver_start';assert(driver:start())
   assert(state~='failed')
   if driver:state()=='done' then state='pending_fence' end
  end)
  if not ok or state=='failed' then return fail() end
  return true
 end
 function owner:update()
  -- The external owner must still fence late callbacks and final logs.
  if state=='pending_fence' then return false,'pending_fence' end
  if state~='active' then return fail() end
  stage='driver_update';local ok,alive=pcall(driver.tick,driver)
  if not ok or alive~=true or state=='failed' then return fail() end
  return false
 end
 function owner:state() return state end
 return owner
end

-- This adapter is opt-in, starts no process, and registers handlers only on
-- owner:start(). The caller must first prove saved marker, load, pause and
-- exclusive event ownership, then keep invoking update via its sole owner.
function M.new_x4(cfg)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 assert(cfg.exclusive_events==true and type(cfg.expected_save_path)=='string'
  and cfg.expected_save_path:sub(1,1)=='/' and cfg.expected_save_path:sub(-11)=='/45841/save')
 for _,name in ipairs({'RegisterEvent','AddUITriggeredEvent','GetCurRealTime','GetComponentData','ConvertStringToLuaID','ConvertIDTo64Bit'}) do
  assert(type(_G[name])=='function',name..' unavailable')
 end
 assert(type(X4LAN_RESOLVE_STRING)=='table' and type(X4LAN_RESOLVE_STRING.parse_hex)=='function' and type(X4LAN_RESOLVE_STRING.actor_u64)=='function')
 assert(type(X4LAN_AUTHORITY_SHIP_ENGINE)=='table' and type(X4LAN_AUTHORITY_SHIP_ENGINE.new)=='function')
 assert(type(cfg.driver_module)=='table' and type(cfg.driver_module.new)=='function' and type(cfg.report)=='function')
 assert(cfg.diagnostic==nil or type(cfg.diagnostic)=='function')
 local function diagnostic(message) if cfg.diagnostic then cfg.diagnostic(message) end end
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
 ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);UIPosRot GetObjectPositionInSector(UniverseID);
 double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local engine=X4LAN_AUTHORITY_SHIP_ENGINE.new()
 local function raw_guard()
  local p=C.GetSaveFolderPath()
  if p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=cfg.expected_save_path
    or not C.IsPlayerValid() or not C.IsGamePaused() then return false end
  local game=tonumber(C.GetCurrentGameTime())
  if not finite(game) or game<0 then return false end
  return true,game
 end
 local function guard()
  local ok,valid,game=pcall(raw_guard)
  if not ok or valid~=true then pcall(diagnostic,'ADAPTER_FAIL guard');if not ok then error('guard failed') end;return false end
  return valid,game
 end
 local function same_context(game)
  local ok,after=guard();assert(ok and after==game,'pause or game time changed')
 end
 local function key(value)
  value=X4LAN_RESOLVE_STRING.actor_u64(value);assert(value,'unsafe local handle')
  local s=tostring(value):gsub('ULL$','')
  assert(s:match('^[1-9]%d*$'),'invalid local handle')
  return s
 end
 local function live(a,s)
  return C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship')
   and C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s
 end
 local snapshot_stage='snapshot_guard'
 local function snapshot_impl(actor_hex,sector_hex)
  snapshot_stage='snapshot_guard';local valid,game=guard();assert(valid)
  snapshot_stage='snapshot_handle';local a=X4LAN_RESOLVE_STRING.parse_hex(actor_hex);local s=X4LAN_RESOLVE_STRING.parse_hex(sector_hex)
  snapshot_stage='snapshot_binding';assert(a and s and live(a,s))
  snapshot_stage='snapshot_position';local p=C.GetObjectPositionInSector(a)
  snapshot_stage='snapshot_recheck';same_context(game);assert(live(a,s))
  snapshot_stage='snapshot_values';local x,y,z=tonumber(p.x),tonumber(p.y),tonumber(p.z)
  assert(finite(x) and finite(y) and finite(z),'nonfinite position')
  snapshot_stage='snapshot_key';return {actor_key=key(a),sector_key=key(s),x=x,y=y,z=z}
 end
 local function snapshot(actor_hex,sector_hex)
  local ok,value=pcall(snapshot_impl,actor_hex,sector_hex)
  if not ok then pcall(diagnostic,'ADAPTER_FAIL '..snapshot_stage);error('snapshot failed') end
  return value
 end
 local count_stage='count_context'
 local function count_impl()
  count_stage='count_context';local valid,game=guard();assert(valid)
  count_stage='count_size';local n=engine.fleet_count('argon')
  assert(finite(n) and n%1==0 and n>=0 and n<200000,'invalid candidate list size')
  count_stage='count_list';local rows,cut=engine.fleet('argon',n+1)
  assert(not cut and type(rows)=='table' and #rows==n and engine.fleet_count('argon')==n,'unstable candidate list')
  local seen,total={},0
  for _,ship in ipairs(rows) do
   count_stage='count_candidate';local id=key(ship);assert(not seen[id] and C.IsValidComponent(ship),'invalid or duplicate candidate');seen[id]=true
   if C.IsComponentOperational(ship) and C.IsComponentClass(ship,'ship') then
    count_stage='count_conversion';local ref=ConvertStringToLuaID(id);assert(ref~=nil and ref~=0)
    assert(key(ref)==id and key(ConvertIDTo64Bit(ref))==id,'candidate conversion mismatch')
    count_stage='count_macro';local macro=GetComponentData(ref,'macro')
    assert(type(macro)=='string' and macro:match('^[%w_%-%.]+$'),'invalid candidate macro')
    if macro=='ship_arg_s_fighter_01_a_macro' then total=total+1 end
   end
  end
  count_stage='count_recheck';same_context(game);assert(engine.fleet_count('argon')==n,'candidate count changed')
  return total
 end
 local function count()
  local ok,value=pcall(count_impl)
  if not ok then pcall(diagnostic,'ADAPTER_FAIL '..count_stage);error('count failed') end
  return value
 end
 local function issue(screen,op,args)
  assert((screen=='X4AuthoritySectorCreateInspect' and (op=='Preflight' or op=='Inspect')) or
   (screen=='X4AuthorityShipCreateReceiver' and (op=='Initialize' or op=='Create')))
  return AddUITriggeredEvent(screen,op,args)~=false
 end
 local opts={enabled=true,epoch=cfg.epoch,nonce=cfg.nonce,macros=cfg.macros,guard=guard,count=count,snapshot=snapshot,
  clock=GetCurRealTime,report=cfg.report,issue=issue,diagnostic=diagnostic}
 return M.new({enabled=true,exclusive_events=true,register=RegisterEvent,diagnostic=diagnostic,
  driver_factory=function()return assert(cfg.driver_module.new(opts)) end})
end
return M
