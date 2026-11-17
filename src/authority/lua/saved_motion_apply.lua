-- Disposable, explicitly enabled one-shot diagnostic. No clearance claim.
-- All actor/sector/zone identities remain local to this process.
local M={}
-- These are two isolated test fixtures, not a general ship-selection API.
local DEFAULT_FIXTURE={index=1318,sector='cluster_115_sector001_macro',code='WRG-830',
 macro='ship_ter_m_corvette_01_a_macro',owner='pioneers'}
local RECOVERY_FIXTURE={name='recovery_enh_870',epoch='4ba7be438ebb04ec5bb85fdb95b5a488',
 index=1318,sector='cluster_06_sector001_macro',code='ENH-870',
 macro='ship_arg_m_trans_container_02_b_macro',owner='antigone'}
local function fixture(name)
 if name==nil then return DEFAULT_FIXTURE end
 if name==RECOVERY_FIXTURE.name then return RECOVERY_FIXTURE end
 error('unknown saved motion fixture')
end
local function finite(x)return type(x)=='number' and x==x and x~=math.huge and x~=-math.huge end
local function token(v,n)return type(v)=='string' and #v==n and v:match('^[0-9a-f]+$')~=nil end
local function natural(v)return type(v)=='string' and v:match('^[1-9]%d*$') and #v<=20 end
local function pose(p)
 if type(p)~='table' then return false end
 for _,k in ipairs({'x','y','z','yaw','pitch','roll'})do if not finite(p[k])then return false end end
 return true
end
local function distance(a,b)return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2)end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 local selected=fixture(c.fixture)
 for _,k in ipairs({'clock','game','guard','issue','inspect','write','log','fault'})do assert(type(c[k])=='function',k)end
 assert(finite(c.timeout) and c.timeout>1 and c.timeout<=30)
 assert(c.request_nonce==nil or token(c.request_nonce,32))
 assert(c.readonly==nil or c.readonly==true)
 assert(c.immediate_readback==nil or c.immediate_readback==true)
 -- Separate experimental observation, never the delayed one-shot receipt.
 assert(c.observe_immediate_only==nil or (c.observe_immediate_only==true and c.immediate_readback==true and not c.readonly))
 local state,busy,used='idle',false,false;local last,deadline,pending,written=nil,nil,nil,false
 local api={}
 local function snapshot()
  return {request=pending.request,epoch=pending.epoch,generation=pending.generation,digest=pending.digest,index=pending.index,
   sequence=pending.sequence,sector_macro=pending.sector_macro,actor_key=pending.actor_key,sector_key=pending.sector_key,
   zone_key=pending.zone_key,target={x=pending.target.x,y=pending.target.y,z=pending.target.z}}
 end
 local function fail(reason)
  if state~='failed' then state='failed';pcall(c.fault,reason,written)end
  return false
 end
 local function check()
  if state=='failed' then return false end
  local old=state;local ok,t=pcall(c.clock)
  if not ok or state~=old or not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline)then return false end
  last=t;local good,v=pcall(c.guard)
  if not good or v~=true or state~=old then return false end
  local again,u=pcall(c.clock)
  if not again or state~=old or not finite(u) or u<t or (deadline and u>=deadline)then return false end
  last=u;return true
 end
 local function report(line)
  local old=state;local ok,v=pcall(c.log,line)
  return ok and v==true and state==old and check()
 end
 local function request(phase)
  local id=(c.request_nonce and c.request_nonce..'-' or '')..pending.request..'-'..phase;pending.id=id
  local old=state;local ok,v=pcall(c.issue,id,snapshot())
  return ok and v==true and state==old and check()
 end
 function api:begin(v)
  if busy or state~='idle' or used then return fail('begin')end
  used=true
  if type(v)~='table' or not token(v.request,32) or not token(v.epoch,32) or not token(v.generation,32) or
     not token(v.digest,64) or v.index~=selected.index or (selected.epoch and v.epoch~=selected.epoch) or
     type(v.sequence)~='number' or v.sequence<1 or v.sequence%1~=0 or
     v.sector_macro~=selected.sector or not natural(v.actor_key) or not natural(v.sector_key) or not natural(v.zone_key) or
     type(v.target)~='table' or not finite(v.target.x) or not finite(v.target.y) or not finite(v.target.z) then return fail('identity')end
  pending={request=v.request,epoch=v.epoch,generation=v.generation,digest=v.digest,index=v.index,sequence=v.sequence,
   sector_macro=v.sector_macro,actor_key=v.actor_key,sector_key=v.sector_key,zone_key=v.zone_key,
   target={x=v.target.x,y=v.target.y,z=v.target.z}}
  local stage='begin_guard';busy=true;local ok=pcall(function()
   assert(check());deadline=last+c.timeout;state='pre';stage='dispatch_guard';assert(check())
   stage='dispatch_issue';assert(request('pre'))
  end);busy=false;if not ok then return fail(stage)end;return true
 end
 function api:event(value)
  if busy or (state~='pre' and state~='post') then return fail('event')end
  local stage=state=='pre' and 'pre_guard' or 'post_guard'
  busy=true;local ok=pcall(function()
   assert(check());stage=state=='pre' and 'pre_response' or 'post_response';assert(value==pending.id..'|ok')
   local before_state=state;stage=state=='pre' and 'pre_inspect' or 'post_inspect';local got,p=pcall(c.inspect,snapshot())
   assert(got and pose(p) and state==before_state and check())
   stage=state=='pre' and 'pre_game' or 'post_game'
   local good,gt=pcall(c.game);assert(good and finite(gt) and gt>=0 and state==before_state and check())
   if state=='pre' then
    stage='pre_distance';local d=distance(p,pending.target);assert(finite(d))
    if c.readonly then
     local result=d<5 and 'NEAR' or (d<=50 and 'READY' or 'FAR')
     stage='preflight_log';assert(report(('PREFLIGHT %s %d %d %s %.17g %.17g %.17g %.17g %.17g %.17g %.17g %.17g %s'):format(
      pending.request,pending.index,pending.sequence,pending.digest,p.x,p.y,p.z,pending.target.x,pending.target.y,pending.target.z,gt,d,result)))
     stage='pre_distance';assert(result~='FAR');state=result=='NEAR' and 'near' or 'ready';deadline=nil;return
    end
    assert(d>=5 and d<=50)
    stage='pre_intent'
    assert(report(('INTENT %s %d %d %s %.17g %.17g %.17g %.17g %.17g %.17g %.17g'):format(
     pending.request,pending.index,pending.sequence,pending.digest,p.x,p.y,p.z,pending.target.x,pending.target.y,pending.target.z,gt)))
    stage='pre_write_marker';assert(report('WRITE_ENTERED '..pending.request))
    stage='write';written=true -- exceptions here can follow a partial effect; never retry.
    local target={x=pending.target.x,y=pending.target.y,z=pending.target.z,
     yaw=p.yaw*180/math.pi,pitch=p.pitch*180/math.pi,roll=p.roll*180/math.pi}
    local w,v=pcall(c.write,snapshot(),target);assert(w and v==true and state=='pre' and check())
    if c.immediate_readback then
     -- Point-in-time observation only: the engine may defer the write or
     -- immediately move the actor. Never treat this as the later readback.
     stage='immediate_inspect';local observed,pnow=pcall(c.inspect,snapshot())
     assert(observed and pose(pnow) and state=='pre' and check())
     stage='immediate_game';local timed,game_now=pcall(c.game)
     assert(timed and finite(game_now) and game_now>=gt and state=='pre' and check())
     stage='immediate_log';assert(report(('IMMEDIATE %s %d %d %s %.17g %.17g %.17g %.17g'):format(
      pending.request,pending.index,pending.sequence,pending.digest,pnow.x,pnow.y,pnow.z,game_now)))
     if c.observe_immediate_only then state='observed';deadline=nil;return end
    end
    pending.write_time=last;pending.game=gt;state='settling'
   else
    if c.immediate_readback then
     stage='post_observation'
     local d=distance(p,pending.target);local elapsed=last-pending.write_time
     assert(finite(d) and finite(elapsed))
     assert(report(('POST_OBSERVED %s %d %d %s %.17g %.17g %.17g %.17g %.17g %.17g %.17g'):format(
      pending.request,pending.index,pending.sequence,pending.digest,p.x,p.y,p.z,gt,pending.game,elapsed,d)))
    end
    stage='post_readback';assert(gt>pending.game and last-pending.write_time>=1 and distance(p,pending.target)<=3)
    stage='post_log';assert(report(('READBACK %s %d %d %s %.17g %.17g %.17g %.17g %.17g'):format(
     pending.request,pending.index,pending.sequence,pending.digest,p.x,p.y,p.z,gt,last-pending.write_time)))
    state='done';deadline=nil
   end
  end);busy=false;if not ok then return fail(stage)end;return true
 end
 function api:tick()
  if busy or state=='idle' or state=='failed' then return fail('tick')end
  local stage='tick_guard';busy=true;local ok=pcall(function()
   assert(check())
   if state=='settling' and last-pending.write_time>=1 then state='post';stage='post_dispatch';assert(request('post'))end
  end);busy=false;if not ok then return fail(stage)end;return true
 end
 function api:state()return state end
 return api
end

function M.new_x4(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local selected=fixture(o.fixture)
 assert(o.test_profile=='45841' and type(o.expected_save_path)=='string' and o.expected_save_path:sub(1,1)=='/' and o.expected_save_path:sub(-11)=='/45841/save')
 assert(type(o.resolve)=='table' and o.resolve==X4LAN_RESOLVE_STRING and type(o.guard)=='function')
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID')then ffi.cdef('typedef uint64_t UniverseID;')end
 if not pcall(ffi.typeof,'UIPosRot')then ffi.cdef('typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;')end
 ffi.cdef[[const char* GetSaveFolderPath(void);bool IsPlayerValid(void);bool IsGamePaused(void);
  bool IsValidComponent(UniverseID);bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
  UniverseID GetContextByClass(UniverseID,const char*,bool);UniverseID GetPlayerControlledShipID(void);
  UniverseID GetPlayerOccupiedShipID(void);UniverseID GetPlayerContainerID(void);const char* GetObjectIDCode(UniverseID);
  UIPosRot GetObjectPositionInSector(UniverseID);void SetObjectSectorPos(UniverseID,UniverseID,UIPosRot);double GetCurrentGameTime(void);]]
 local C=ffi.C;local c={};for k,v in pairs(o)do c[k]=v end
 local function key(v)local n=o.resolve.actor_u64(v);return n and tostring(n):gsub('ULL$','') or nil end
 local function ref(text)
  assert(natural(text));local x=ConvertStringToLuaID(text);local kind=type(x)
  if kind=='number' or kind=='cdata' then assert(key(x)==text)else assert(kind=='userdata')end
  local id=o.resolve.actor_u64(ConvertIDTo64Bit(x));assert(id and key(id)==text)
  return x,id
 end
 assert(o.md_issue==nil or type(o.md_issue)=='function')
 local md_issue=o.md_issue or AddUITriggeredEvent
 local external=o.guard
 c.guard=function()
  local p=C.GetSaveFolderPath()
  if p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=o.expected_save_path or
     not C.IsPlayerValid() or C.IsGamePaused() or external()~=true then return false end
  local q=C.GetSaveFolderPath()
  return q~=nil and q~=ffi.NULL and ffi.string(q):gsub('\\','/'):gsub('/+$','')==o.expected_save_path and C.IsPlayerValid() and not C.IsGamePaused()
 end
 c.clock=GetCurRealTime;c.game=function()return tonumber(C.GetCurrentGameTime())end
 local function ids(p)
  local ar,a=ref(p.actor_key);local sr,s=ref(p.sector_key);local zr,z=ref(p.zone_key)
  return ar,a,sr,s,zr,z
 end
 c.issue=function(id,p)
  local ar,a,sr,s,zr,z=ids(p);assert(a and s and z)
  local args={request_id=id,epoch=p.epoch,index=p.index,actor=ar,sector=sr,zone=zr}
  if selected.name then args.fixture=selected.name end
  local accepted = md_issue('X4AuthoritySavedMotionApply','Inspect',args)
  if o.md_issue then return accepted == true end
  return accepted ~= false
 end
 local function live(p)
  local ar,a,sr,s,zr,z=ids(p)
  assert(c.guard() and C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship'))
  assert(C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s)
  assert(C.IsValidComponent(z) and C.IsComponentClass(z,'zone') and C.GetContextByClass(a,'zone',false)==z)
  local controlled,occupied,container=C.GetPlayerControlledShipID(),C.GetPlayerOccupiedShipID(),C.GetPlayerContainerID()
  assert(controlled~=a and occupied~=a and container~=a and container~=0 and C.IsValidComponent(container))
  local own=C.GetContextByClass(container,'ship',true)
  if own~=0 then assert(own~=a)else assert(C.GetContextByClass(container,'station',true)~=0)end
  local docked,docking,stored=GetComponentData(ar,'isdocked','isdocking','isinternallystored')
  assert(docked==false and docking==false and stored==false)
  local macro,owner=GetComponentData(ar,'macro','owner');assert(macro==selected.macro and owner==selected.owner)
  local sector_macro=GetComponentData(sr,'macro');assert(sector_macro==p.sector_macro)
  local code=C.GetObjectIDCode(a);assert(code~=nil and code~=ffi.NULL and ffi.string(code)==selected.code)
  assert(c.guard());return a,s
 end
 c.inspect=function(p)
  local a=live(p);local x=C.GetObjectPositionInSector(a);assert(live(p)==a)
  return {x=tonumber(x.x),y=tonumber(x.y),z=tonumber(x.z),yaw=tonumber(x.yaw),pitch=tonumber(x.pitch),roll=tonumber(x.roll)}
 end
 c.write=function(p,t)
  local a,s=live(p);C.SetObjectSectorPos(a,s,ffi.new('UIPosRot',t));assert(live(p)==a);return true
 end
 return M.new(c)
end
X4LAN_SAVED_MOTION_APPLY=M
return M
