-- Private opt-in continuation of the existing single control/load update owner.
local M={}
local function finite(x)return type(x)=='number' and x==x and math.abs(x)<math.huge end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 for _,k in ipairs({'control_tick','control_state','control_outcome','handoff','make','resume','is_paused','clock','log'})do assert(type(o[k])=='function')end
 local busy,failed=false,false;local phase='control';local observer,last_sample,seq=nil,nil,0
 local labels={'neutral','before','after'};local api={}
 local function fail()if not failed then failed=true;phase='failed';pcall(o.log,'ERROR FAULT')end;return false end
 local function run(f)
  if failed or busy then return fail()end;busy=true
  local ok=pcall(function()f();assert(not failed)end);busy=false
  if not ok or failed then return fail()end;return true
 end
 function api:tick()
  return run(function()
   if phase=='control' then
    assert(o.control_tick()==true and not failed)
    if o.control_state()=='done' then
     local status=o.control_outcome();assert(status=='controlled' or status=='inconclusive')
     if status=='inconclusive' then phase='inconclusive';o.log('INCONCLUSIVE');return end
     local target=o.handoff();assert(target and not failed);observer=o.make(target);assert(observer and not failed)
     assert(observer:arm() and not failed)
     local t,g=o.clock();assert(finite(t) and finite(g) and observer:tick() and not failed)
     phase='armed';o.log(('ARMED %.17g %.17g'):format(t,g))
    end
   elseif phase=='armed' then
    assert(observer:begin_resume() and not failed);phase='resuming';o.log('RESUME_INTENT')
    assert(not failed and o.is_paused()==true and observer:tick() and not failed and o.is_paused()==true)
    assert(o.resume()==true and not failed);o.log('RESUME_RETURNED')
   elseif phase=='resuming' then
    assert(observer:tick() and not failed)
    if observer:state()=='ready' then
     local t,g=o.clock();assert(finite(t) and finite(g) and observer:tick() and not failed)
     phase='ready';o.log(('RUNNING %.17g %.17g'):format(t,g))
    end
   elseif phase=='ready' then
    assert(observer:tick() and not failed)
    local t,g=o.clock();assert(finite(t) and finite(g))
    if not last_sample or (t>last_sample.real_after and g>last_sample.game_after) then
     seq=seq+1;assert(seq<=3);phase='waiting';assert(observer:request(labels[seq]) and not failed)
    end
   elseif phase=='waiting' then assert(observer:tick() and not failed)
   elseif phase=='report' then
    assert(observer:tick() and not failed);phase='done';o.log('DONE');assert(not failed and observer:tick() and not failed);o.log('FENCED')
   elseif phase=='done' then assert(observer:tick() and not failed)
   elseif phase=='inconclusive' then assert(o.control_tick()==true and not failed);phase='inconclusive_done';o.log('DONE')
   elseif phase=='inconclusive_done' then assert(o.control_tick()==true and not failed)
   else error('unexpected phase') end
  end)
 end
 function api:response(v)
  return run(function()
   assert(phase=='waiting' and observer);local ok,r=observer:response(v);assert(ok and not failed and type(r)=='table' and r.sequence==seq and r.label==labels[seq])
   last_sample=r;o.log(('SAMPLE %d %.17g %.17g %.17g %.17g %.17g %.17g %.17g %.17g %.17g %.17g'):format(seq,r.real_before,r.real_after,r.game_before,r.game_after,r.x,r.y,r.z,r.yaw,r.pitch,r.roll))
   assert(not failed and observer:tick() and not failed)
   phase=seq==3 and 'report' or 'ready'
  end)
 end
 function api:refused()return fail()end
 function api:state()return phase end
 return api
end
X4LAN_AUTHORITY_PLAYER_FLIGHT_LIVE_OWNER=M
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_player_flight_live~=true then return M end
local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID')then ffi.cdef('typedef uint64_t UniverseID;')end
ffi.cdef[[UniverseID GetContextByClass(UniverseID,const char*,bool);bool IsValidComponent(UniverseID);
 bool IsComponentClass(UniverseID,const char*);bool IsGamePaused(void);double GetCurrentGameTime(void);]]
local C=ffi.C
assert(type(Unpause)=='function')
local app=M.new{enabled=true,control_tick=function()X4LAN_PLAYER_CONTROL_LIVE_TICK();return true end,
 control_state=X4LAN_PLAYER_CONTROL_LIVE_STATE,control_outcome=X4LAN_PLAYER_CONTROL_LIVE_OUTCOME,
 handoff=X4LAN_PLAYER_CONTROL_LIVE_HANDOFF,
 make=function(target)
  local zone=C.GetContextByClass(target.ship,'zone',false)
  assert(zone~=0 and C.IsValidComponent(zone) and C.IsComponentClass(zone,'zone'))
  return X4LAN_AUTHORITY_PLAYER_FLIGHT_OBSERVER.new_x4{enabled=true,epoch=cfg.authority_sector_epoch,
   nonce=cfg.authority_player_flight_nonce,timeout=cfg.authority_player_flight_timeout,
   expected_save_path=cfg.authority_read_save_path,target=target.ship,sector=target.sector,parent_zone=zone,
   owner_id='player',confirmed=function()return true end,external_guard=function()return true end}
 end,
 resume=function()Unpause();return true end,
 is_paused=function()return C.IsGamePaused()end,
 clock=function()return GetCurRealTime(),tonumber(C.GetCurrentGameTime())end,
 log=function(s)DebugError('[X4LAN] AUTH_PLAYER_FLIGHT_LIVE '..s)end}
RegisterEvent('X4AuthorityPlayerFlightObserver.Result',function(_,v)app:response(v)end)
RegisterEvent('X4AuthorityPlayerFlightObserver.Refused',function()app:refused()end)
function X4LAN_PLAYER_FLIGHT_LIVE_TICK()if not app:tick() then error('flight observation failed')end end
return M
