-- Default-off, disposable one-process fixture/seat diagnostic. No update owner installed here.
local M={}
local function token(s) return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<math.huge end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.nonce) and finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,n in ipairs({'guard','issue','make_seat','log','live'}) do assert(type(o[n])=='function') end
 local phase='new';local failed=false;local busy=false;local first,last,game,actor,sector,seat,result
 local reasons={callback_failed=true,state_changed=true,reentrant=true,clock_failed=true,
  clock_or_timeout=true,guard_failed=true,pause_or_process_guard=true,deadline=true,
  dispatch=true,not_idle=true,unexpected_response=true,response_type=true,response_mismatch=true,
  getter_unavailable=true,identity_unavailable=true,duplicate_ship=true,
  positive_control_inconclusive=true,sector_mismatch=true,not_waiting=true,md_refused=true,
  inspect_callback_failed=true,inspect_state_changed=true,inspect_reentrant=true}
 local function fail(code)
  if not failed then failed=true;phase='failed';pcall(o.log,'ERROR '..code) end
  return false
 end
 local function seat_fail(prefix,reason)
  return fail(prefix..'_'..(type(reason)=='string' and reasons[reason] and reason:upper() or 'UNKNOWN'))
 end
 local function checked()
  local t,g,a,s=o.guard()
  assert(finite(t) and t>=0 and finite(g) and g>=0 and type(a)=='string' and a~='' and type(s)=='string' and s~='')
  first=first or t;assert((not last or t>=last) and t-first<o.timeout);last=t
  if game then assert(game==g and actor==a and sector==s) else game,actor,sector=g,a,s end
  if result then
   assert(o.live(result)==true)
   local t2,g2,a2,s2=o.guard()
   assert(finite(t2) and t2>=last and t2-first<o.timeout and g2==game and a2==actor and s2==sector)
   last=t2
  end
 end
 local function action(fn,label)
  if failed then return false end
  if busy then return fail('REENTRANT') end
  busy=true
  local ok=pcall(checked)
  if not ok or failed then busy=false;return fail('PRE_GUARD') end
  local stage=label
  local function setstage(s) stage=s end
  ok=pcall(fn,setstage)
  if not ok or failed then busy=false;return fail(stage) end
  ok=pcall(checked);busy=false
  if not ok or failed then return fail('POST_GUARD') end
  return true
 end
 local api={}
 function api:tick()
  return action(function(setstage)
   if phase=='new' then
    phase='preflight';assert(o.issue('X4AuthorityPlayerSeatExperiment','Preflight',{epoch=o.epoch,request_id=o.nonce})==true)
   elseif phase=='create' then
    phase='created_wait';assert(o.issue('X4AuthorityPlayerSectorFixture','Create',{epoch=o.epoch})==true)
   elseif phase=='seat_start' then
    setstage('SEAT_CONSTRUCT');seat=o.make_seat();assert(seat);phase='seat_wait'
    setstage('SEAT_START');local ok,why=seat:start();if not ok then seat_fail('SEAT_START',why);error('seat') end
   elseif phase=='seat_wait' then
    setstage('SEAT_TICK');local ok,why=seat:tick();if not ok then seat_fail('SEAT_TICK',why);error('seat') end
   elseif phase=='report' then
    assert(result and result.classification=='inconclusive' and result.positive_control_observed==true and
     result.seat_free_proven==false and result.player_control_proven==false and result.save_authorized==false)
    local r=result.rows;assert(type(r)=='table' and #r==3 and r[1].actor_key==actor and r[1].sector_key==sector)
    assert(r[1].assigned=='present' and r[1].reservation=='occupied')
    assert(r[2].assigned=='nil_observed' and r[2].reservation=='empty' and r[3].assigned=='nil_observed' and r[3].reservation=='empty')
    checked();phase='done';o.log('POSITIVE');o.log('NEGATIVE1');o.log('NEGATIVE2');o.log('DONE')
   elseif phase~='preflight' and phase~='created_wait' and phase~='done' then error('state') end
  end,'TICK')
 end
 function api:preflight(v)
  return action(function()
   assert(phase=='preflight' and v==o.nonce..'|'..o.epoch..'|ok');phase='create';o.log('PREFLIGHT')
  end,'PREFLIGHT_RESULT')
 end
 function api:created(v)
  return action(function() assert(phase=='created_wait' and type(v)=='number' and v==2);phase='seat_start';o.log('CREATED') end,'CREATED_RESULT')
 end
 function api:response(v)
  return action(function()
   assert(phase=='seat_wait' and seat);local ok,r=seat:response(v)
   if not ok then seat_fail('SEAT_RESULT',r);error('seat') end
   assert(not failed)
   if seat:state()=='done' then assert(type(r)=='table');result=r;phase='report' end
  end,'SEAT_RESULT')
 end
 function api:refused(source)
  if source=='preflight' then return fail('PREFLIGHT_REFUSED') end
  if source=='fixture' then return fail('FIXTURE_REFUSED') end
  return fail('SEAT_REFUSED')
 end
 function api:state() return phase end
 return api
end
X4LAN_AUTHORITY_PLAYER_SEAT_EXPERIMENT=M
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_player_seat_experiment~=true then return M end
local ffi=require('ffi')
if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);double GetCurrentGameTime(void);
 const char* GetSaveFolderPath(void);]]
local C=ffi.C
local epoch,nonce=cfg.authority_sector_epoch,cfg.authority_player_seat_nonce
local function norm(x) return tostring(x):gsub('ULL$','') end
local function guard()
 local before=GetCurRealTime();local p=C.GetSaveFolderPath()
 assert(p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 assert(C.IsPlayerValid() and C.IsGamePaused())
 local a,s,_,initial=X4LAN_SECTOR_READ_EXPORT();local g=tonumber(C.GetCurrentGameTime())
 assert(g==initial and C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and
  C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s)
 local after=GetCurRealTime();assert(finite(before) and finite(after) and after>=before and C.IsGamePaused())
 return after,g,norm(a),norm(s)
end
local app=M.new{enabled=true,epoch=epoch,nonce=nonce,timeout=cfg.authority_player_seat_timeout,
 guard=guard,live=function(result)
  for _,row in ipairs(result.rows) do
   local aid=ConvertIDTo64Bit(ConvertStringToLuaID(row.actor_key))
   local sid=ConvertIDTo64Bit(ConvertStringToLuaID(row.sector_key))
   assert(norm(aid)==row.actor_key and norm(sid)==row.sector_key)
   local a=ffi.new('UniverseID',aid);local s=ffi.new('UniverseID',sid)
   assert(C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and
    C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s)
  end
  return true
 end,issue=function(screen,operation,args) return AddUITriggeredEvent(screen,operation,args)~=false end,
 make_seat=function() return X4LAN_AUTHORITY_PLAYER_SEAT_CALIBRATION.new_x4{enabled=true,epoch=epoch,nonce=nonce,
  timeout=cfg.authority_player_seat_timeout,expected_save_path=cfg.authority_read_save_path} end,
 log=function(s) DebugError('[X4LAN] AUTH_PLAYER_SEAT_EXPERIMENT '..s) end}
RegisterEvent('X4AuthorityPlayerSeatExperiment.Preflight',function(_,v) app:preflight(v) end)
RegisterEvent('X4AuthorityPlayerSeatExperiment.Refused',function() app:refused('preflight') end)
RegisterEvent('X4AuthorityPlayerSectorFixture.Created',function(_,v) app:created(v) end)
RegisterEvent('X4AuthorityPlayerSectorFixture.Refused',function() app:refused('fixture') end)
RegisterEvent('X4AuthorityPlayerSeatCalibration.Result',function(_,v) app:response(v) end)
RegisterEvent('X4AuthorityPlayerSeatCalibration.Refused',function() app:refused('seat') end)
function X4LAN_PLAYER_SEAT_EXPERIMENT_TICK() if not app:tick() then error('player seat experiment failed') end end
return M
