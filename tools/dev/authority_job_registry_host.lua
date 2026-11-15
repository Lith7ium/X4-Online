-- Opt-in, disposable one-process observer. Import starts no game or callbacks.
-- The supervisor owns isolation, a fresh registry/queue and process cleanup.
local M={}
local REG='X4AuthorityShipRegistry'
local QUEUE='X4AuthorityJobShipEvents'
local function finite(n) return type(n)=='number' and n==n and n>=0 and n<math.huge end
local function natural(n) return finite(n) and n%1==0 and n<=9007199254740991 end

function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(type(o.epoch)=='string' and #o.epoch==32 and o.epoch:match('^[0-9a-f]+$'))
 assert(type(o.baseline)=='table' and #o.baseline<=64 and natural(o.capacity) and o.capacity>=1 and o.capacity<=1024)
 for k in pairs(o.baseline) do assert(natural(k) and k>=1 and k<=#o.baseline,'baseline must be a dense array') end
 assert(finite(o.window) and o.window>0 and finite(o.timeout) and o.timeout>0)
 for _,name in ipairs({'register','trigger','convert64','to_lua_id','valid','clock','report','done','fault','can_observe'}) do
  assert(type(o[name])=='function',name..' required')
 end
 assert(type(o.probe)=='table' and type(o.probe.new)=='function')
 local phase='new';local failed=false;local started,deadline,last_clock
 local baseline,index,seen={},1,{}
 local driver,stop_at,hard_stop,next_poll,stats,records=nil,nil,nil,0,nil,0
 local function now()
  local value=o.clock();assert(finite(value) and (not last_clock or value>=last_clock),'clock invalid')
  last_clock=value;return value
 end
 local function issue(screen,op,args)
  local ok,result=pcall(o.trigger,screen,op,args);return ok and result~=false
 end
 local function fail(reason)
  if not failed then
   failed=true;phase='failed'
   if driver then pcall(function() driver:timeout() end)
   else pcall(issue,QUEUE,'Abort',{epoch=o.epoch}) end
   pcall(o.fault,reason)
  end
 end
 local function actor_key(actor)
  local value=o.convert64(actor)
  assert(value~=nil and value~=false and value~=0,'invalid actor')
  local key=tostring(value):gsub('ULL$','')
  assert(key:match('^[1-9]%d*$'),'invalid decimal actor identity')
  return key
 end
 local function md_actor(actor,key)
  assert(actor_key(actor)==key)
  local value=o.to_lua_id(key)
  assert(value~=nil and value~=false and value~=0 and actor_key(value)==key,'invalid actor conversion')
  return value
 end
 local function request(screen,operation,args,next_phase)
  phase=next_phase;deadline=now()+o.timeout
  assert(issue(screen,operation,args),'request dispatch failed')
 end
 local function baseline_next()
  if index>#o.baseline then
   request(QUEUE,'Initialize',{epoch=o.epoch,capacity=o.capacity},'queue_init')
   return
  end
  local actor=o.baseline[index];local key=actor_key(actor)
  assert(not seen[key] and o.valid(actor)==true,'invalid or duplicate baseline actor')
  seen[key]=true
  request(REG,'Enroll',{epoch=o.epoch,ship=md_actor(actor,key)},'baseline')
 end
 local status_order={'Epoch','Observed','Acknowledged','Depth','Inflight','Reason'}
 local function status()
  stats={};request(QUEUE,'Status',{},'status')
 end
 local function handle(screen,name,value)
  if failed then return end
  local t=now()
  if started and o.can_observe()~=true then error('source observation stopped') end
  if hard_stop and t>hard_stop then error('observation drain timeout') end
  if deadline and t>deadline then error('response timeout') end
  if name=='Faulted' or name=='Refused' or name=='Unavailable' or name=='Uninitialized' then error('MD fault or refusal') end
  if phase=='registry_init' and screen==REG and name=='Initialized' then
   assert(value==o.epoch);baseline_next();return
  end
  if phase=='baseline' and screen==REG and name=='Enrolled' then
   assert(value==index and o.valid(o.baseline[index])==true)
   local key=actor_key(o.baseline[index]);assert(seen[key]);baseline[key]=value
   index=index+1;baseline_next();return
  end
  if phase=='queue_init' and screen==QUEUE and name=='Initialized' then
   assert(value==o.epoch and o.can_observe()==true,'source is not running');started=t;stop_at=t+o.window;hard_stop=stop_at+o.timeout
   driver=o.probe.new({enabled=true,epoch=o.epoch,last=#o.baseline,baseline=baseline,
    issue=issue,key=actor_key,to_md_actor=md_actor,valid=o.valid,
    report=function(row) assert(o.report(row)==true);records=records+1;return true end})
   status();return
  end
  if phase=='status' and screen==QUEUE then
   local expected=status_order[#stats+1]
   if name==expected then
    -- Preserve empty reason as a value so the ordered field count is stable.
    stats[#stats+1]={name=name,value=value};return
   end
   assert(name=='Healthy' and #stats==#status_order,'invalid status sequence')
   local epoch=stats[1].value;local observed=stats[2].value
   local ack=stats[3].value;local depth=stats[4].value;local inflight=stats[5].value
   assert(epoch==o.epoch and natural(observed) and natural(ack) and natural(depth) and natural(inflight))
   assert(stats[6].value==nil or stats[6].value=='','healthy queue has fault reason')
   assert(ack==records and observed==ack+depth and depth<=o.capacity and inflight==0,'queue state mismatch')
   deadline=nil
   if t>=stop_at and depth==0 then
    phase='done'
    assert(o.done({observed=observed,acknowledged=ack,baseline_count=#o.baseline,
     classification=observed==0 and 'inconclusive_no_events' or 'local_activations_observed',
     birth_confirmed=false,delivery_confirmed=false,coverage='unknown'})==true)
   else phase='ready_front' end
   return
  end
  if phase=='front' and (screen==QUEUE or screen==REG) then
   local ok,reason=driver:event(name,value);assert(ok,reason)
   if driver:state()=='idle' then phase='waiting';deadline=nil;next_poll=t+.1 end
   return
  end
  error('unexpected MD response')
 end
 local api={}
 function api:start()
  if phase~='new' then fail('repeated start');return false end
  local ok,err=pcall(function()
   for _,item in ipairs({{REG,'Initialized'},{REG,'Enrolled'},{REG,'Faulted'},{REG,'Refused'},{REG,'Unavailable'},
      {QUEUE,'Initialized'},{QUEUE,'Epoch'},{QUEUE,'Observed'},{QUEUE,'Acknowledged'},
      {QUEUE,'Depth'},{QUEUE,'Inflight'},{QUEUE,'Reason'},{QUEUE,'Healthy'},
      {QUEUE,'Sequence'},{QUEUE,'Actor'},{QUEUE,'Empty'},{QUEUE,'Acked'},
      {QUEUE,'Faulted'},{QUEUE,'Refused'},{QUEUE,'Uninitialized'}}) do
    local screen,name=item[1],item[2]
    o.register(screen..'.'..name,function(_,value)
     local good,why=pcall(handle,screen,name,value);if not good then fail(tostring(why)) end
    end)
   end
   request(REG,'Initialize',{epoch=o.epoch},'registry_init')
  end)
  if not ok then fail(tostring(err));return false end
  return true
 end
 function api:tick()
  if failed or phase=='done' then return false,phase end
  local ok,err=pcall(function()
   local t=now()
   if started and not o.can_observe() then error('source observation stopped') end
   if hard_stop and t>hard_stop then error('observation drain timeout') end
   if deadline and t>deadline then error('response timeout') end
   if phase=='waiting' and t>=next_poll then
    -- Recheck queue and registry fault status at least once per polling turn.
    status()
   elseif phase=='ready_front' then
    phase='front';deadline=t+o.timeout;assert(driver:front())
   end
  end)
  if not ok then fail(tostring(err));return false,'failed' end
  return true,phase
 end
 function api:state() return phase end
 return api
end

-- Bind only the required documented-by-experiment X4 UI/FFI calls. The caller
-- supplies a single onUpdate owner, disposable path, baseline and supervisor.
function M.new_x4(cfg)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 assert(type(cfg.expected_save_path)=='string' and cfg.expected_save_path:sub(1,1)=='/'
  and cfg.expected_save_path:sub(-11)=='/45841/save')
 for _,name in ipairs({'RegisterEvent','AddUITriggeredEvent','ConvertIDTo64Bit','ConvertStringToLuaID','GetCurRealTime'}) do
  assert(type(_G[name])=='function',name..' unavailable')
 end
 local ffi=require('ffi')
 if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 ffi.cdef[[const char* GetSaveFolderPath(void); bool IsGamePaused(void); bool IsPlayerValid(void);
 bool IsValidComponent(UniverseID); bool IsComponentOperational(UniverseID); bool IsComponentClass(UniverseID,const char*);]]
 local C=ffi.C
 local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.expected_save_path)
 local opts={};for k,v in pairs(cfg) do opts[k]=v end
 opts.register=RegisterEvent;opts.trigger=AddUITriggeredEvent
 opts.convert64=ConvertIDTo64Bit;opts.to_lua_id=ConvertStringToLuaID;opts.clock=GetCurRealTime
 opts.can_observe=function()
  local current=C.GetSaveFolderPath()
  return current~=nil and current~=ffi.NULL and ffi.string(current):gsub('\\','/'):gsub('/+$','')==cfg.expected_save_path
   and C.IsPlayerValid() and not C.IsGamePaused()
 end
 opts.valid=function(actor)
  local id=ffi.new('UniverseID',ConvertIDTo64Bit(actor))
  return C.IsPlayerValid() and C.IsValidComponent(id) and C.IsComponentOperational(id) and C.IsComponentClass(id,'ship')
 end
 return M.new(opts)
end
X4LAN_AUTHORITY_JOB_REGISTRY_HOST=M
return M
