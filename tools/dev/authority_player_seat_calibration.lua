-- Default-off, read-only diagnostic. Import registers no events or update loop.
-- A private owner must serialize requests, supply fresh nonce and observe pause.
local M={}
local SCREEN='X4AuthorityPlayerSeatCalibration'
local function token(s) return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function hex(s) return type(s)=='string' and s:match('^0[xX][0-9a-fA-F]+$')~=nil and #s<=18 end

function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.nonce) and finite(o.timeout) and o.timeout>0 and o.timeout<=120)
 for _,name in ipairs({'issue','clock','guard','inspect'}) do assert(type(o[name])=='function',name..' required') end
 local state='idle';local generation={};local busy=false;local last=nil;local deadline=nil
 local slot=0;local rows={};local api={}
 local function fail(reason) state='failed';generation={};return false,reason end
 local function call(fn,...)
  if busy then return fail('reentrant') end
  local current,phase=generation,state;busy=true;local ok,value=pcall(fn,...);busy=false
  if current~=generation or phase~=state then return fail('state_changed') end
  if not ok then return fail('callback_failed') end
  return true,value
 end
 local function check()
  if state=='failed' or state=='closed' then return false,'unavailable' end
  local ok,t=call(o.clock)
  if not ok then return false,'clock_failed' end
  if not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return fail('clock_or_timeout') end
  last=t
  local good,valid=call(o.guard)
  if not good then return false,'guard_failed' end
  if valid~=true then return fail('pause_or_process_guard') end
  return true
 end
 local function request()
  if not check() then return false end
  local request_id=o.nonce..'-'..slot
  state='waiting';generation={};deadline=last+o.timeout
  if not finite(deadline) then return fail('deadline') end
  local ok,sent=call(o.issue,SCREEN,'Read',{epoch=o.epoch,slot=slot,request_id=request_id})
  if not ok then return false end
  if sent~=true then return fail('dispatch') end
  return check()
 end
 function api:start()
  if state~='idle' then return fail('not_idle') end
  return request()
 end
 function api:response(value)
  if state~='waiting' then return fail('unexpected_response') end
  if not check() then return false end
  if type(value)~='string' or #value>256 then return fail('response_type') end
  local request_id,epoch,raw_slot,actor,sector,reservation=value:match('^([0-9a-f%-]+)|([0-9a-f]+)|([012])|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([a-z]+)$')
  if request_id~=o.nonce..'-'..slot or epoch~=o.epoch or raw_slot~=tostring(slot) or
     not hex(actor) or not hex(sector) or (reservation~='empty' and reservation~='occupied') then
   return fail('response_mismatch')
  end
  local ok,sample=call(o.inspect,actor,sector)
  if not ok then return false end
  if type(sample)~='table' or (sample.assigned~='present' and sample.assigned~='nil_observed') or
     not finite(sample.x) or not finite(sample.y) or not finite(sample.z) or not finite(sample.hull) then
   return fail('getter_unavailable')
  end
  if not check() then return false end
  local normalized_actor=sample.actor_key;local normalized_sector=sample.sector_key
  if type(normalized_actor)~='string' or normalized_actor=='' or type(normalized_sector)~='string' or normalized_sector=='' then
   return fail('identity_unavailable')
  end
  for _,old in ipairs(rows) do if old.actor_key==normalized_actor then return fail('duplicate_ship') end end
  rows[#rows+1]={slot=slot,actor_key=normalized_actor,sector_key=normalized_sector,
                assigned=sample.assigned,reservation=reservation,x=sample.x,y=sample.y,z=sample.z,hull=sample.hull}
  if slot==0 and (sample.assigned~='present' or reservation~='occupied') then return fail('positive_control_inconclusive') end
  if slot==2 then
   if rows[2].sector_key==rows[3].sector_key or rows[1].sector_key~=rows[3].sector_key then return fail('sector_mismatch') end
   state='done';deadline=nil
   return true,{classification='inconclusive',positive_control_observed=true,rows=rows,
                seat_free_proven=false,player_control_proven=false,save_authorized=false}
  end
  slot=slot+1;deadline=nil;state='next'
  return request()
 end
 function api:tick()
  if state=='waiting' then return check() end
  if state=='done' then return true end
  return fail('not_waiting')
 end
 function api:refused() return fail('md_refused') end
 function api:close() state='closed';generation={};deadline=nil;return true end
 function api:state() return state end
 return api
end

-- The owner provides X4LAN_RESOLVE_STRING.parse_hex and routes exactly one
-- Result or Refused event into the instance. No callbacks are registered here.
function M.new_x4(cfg)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 assert(type(cfg.expected_save_path)=='string' and cfg.expected_save_path:sub(1,1)=='/' and
        cfg.expected_save_path:sub(-11)=='/45841/save')
 for _,name in ipairs({'AddUITriggeredEvent','ConvertStringToLuaID','ConvertIDTo64Bit','GetCurRealTime','GetComponentData'}) do
  assert(type(_G[name])=='function',name..' unavailable')
 end
 assert(type(X4LAN_RESOLVE_STRING)=='table' and type(X4LAN_RESOLVE_STRING.parse_hex)=='function')
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof,'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
 ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);bool IsValidComponent(UniverseID);
 bool IsComponentOperational(UniverseID);bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);UIPosRot GetObjectPositionInSector(UniverseID);
 const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local o={};for k,v in pairs(cfg) do o[k]=v end
 o.clock=GetCurRealTime
 o.guard=function()
  local p=C.GetSaveFolderPath()
  return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.expected_save_path
         and C.IsPlayerValid() and C.IsGamePaused()
 end
 o.issue=function(screen,operation,args) return AddUITriggeredEvent(screen,operation,args)~=false end
 o.inspect=function(actor_hex,sector_hex)
  local actor=X4LAN_RESOLVE_STRING.parse_hex(actor_hex);local sector=X4LAN_RESOLVE_STRING.parse_hex(sector_hex)
  assert(actor and sector and C.IsValidComponent(actor) and C.IsComponentOperational(actor)
   and C.IsComponentClass(actor,'ship') and C.IsValidComponent(sector) and C.IsComponentClass(sector,'sector')
   and C.GetContextByClass(actor,'sector',false)==sector)
  local key=tostring(actor):gsub('ULL$','');local sector_key=tostring(sector):gsub('ULL$','')
  local id=ConvertStringToLuaID(key);assert(id~=nil and id~=false)
  local roundtrip=ConvertIDTo64Bit(id);assert(tostring(roundtrip):gsub('ULL$','')==key)
  local ok,pilot=pcall(GetComponentData,id,'assignedpilot');assert(ok)
  local assigned='nil_observed'
  if pilot~=nil then
   local value=ConvertIDTo64Bit(pilot);assert(value~=nil and tostring(value):gsub('ULL$','')~='0')
   local pilot_id=ffi.new('UniverseID',value);assert(C.IsValidComponent(pilot_id))
   assigned='present'
  end
  local success,hull=pcall(GetComponentData,id,'hullpercent');assert(success and finite(hull))
  local p=C.GetObjectPositionInSector(actor)
  assert(o.guard() and C.IsValidComponent(actor) and C.IsComponentOperational(actor)
   and C.GetContextByClass(actor,'sector',false)==sector)
  return {actor_key=key,sector_key=sector_key,assigned=assigned,hull=hull,
          x=tonumber(p.x),y=tonumber(p.y),z=tonumber(p.z)}
 end
 return M.new(o)
end
X4LAN_AUTHORITY_PLAYER_SEAT_CALIBRATION=M
return M
