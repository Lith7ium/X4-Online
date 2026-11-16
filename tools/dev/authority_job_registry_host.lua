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
 assert(o.expose_actor==nil or type(o.expose_actor)=='boolean')
 assert(o.defer_ack==nil or type(o.defer_ack)=='boolean')
 if o.defer_ack then
  assert(finite(o.delivery_timeout) and o.delivery_timeout>0 and o.delivery_timeout<=600)
  assert(type(o.queue_acked)=='function','queue_acked required')
  assert(o.can_hold_delivery==nil or type(o.can_hold_delivery)=='function')
 else assert(o.delivery_timeout==nil and o.can_hold_delivery==nil,'delivery options require deferred ACK') end
 local attach=o.attach_saved_registry==true
 assert(o.attach_saved_registry==nil or type(o.attach_saved_registry)=='boolean')
 if attach then
  assert(o.exclusive_registry_consumer==true and natural(o.expected_last) and #o.baseline==0 and type(o.can_attach)=='function',
   'attach requires exclusive consumer, expected last, paused guard and empty local baseline')
 else
  assert(o.exclusive_registry_consumer==nil and o.expected_last==nil and o.can_attach==nil, 'attach options require attach mode')
 end
 for k in pairs(o.baseline) do assert(natural(k) and k>=1 and k<=#o.baseline,'baseline must be a dense array') end
 assert(finite(o.window) and o.window>0 and finite(o.timeout) and o.timeout>0)
 for _,name in ipairs({'register','trigger','convert64','to_lua_id','valid','clock','report','done','fault','can_observe'}) do
  assert(type(o[name])=='function',name..' required')
 end
 assert(type(o.probe)=='table' and type(o.probe.new)=='function')
 local phase='new';local failed=false;local started,deadline,last_clock
 local baseline,index,seen={},1,{}
 local driver,stop_at,hard_stop,next_poll,stats,records=nil,nil,nil,0,nil,0
 local initial_last=attach and o.expected_last or #o.baseline
 local queue_init_attempted=false
 local delivery,notifying=nil,false
 local function source_ok()
  local before=phase
  local running=o.can_observe()
  if failed or phase~=before then return false end
  if running==true then return true end
  if not (o.defer_ack and type(o.can_hold_delivery)=='function' and
   (phase=='await_delivery' or (phase=='front' and driver and driver:state()=='ack') or notifying)) then return false end
  local held=o.can_hold_delivery()
  return held==true and not failed and phase==before
 end
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
   elseif not attach or queue_init_attempted then pcall(issue,QUEUE,'Abort',{epoch=o.epoch}) end
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
 local function begin_observation(t)
  assert(o.can_observe()==true,'source is not running')
  started=t;stop_at=t+o.window;hard_stop=stop_at+o.timeout
  driver=o.probe.new({enabled=true,epoch=o.epoch,last=initial_last,baseline=baseline,expose_actor=o.expose_actor,defer_ack=o.defer_ack,
   issue=issue,key=actor_key,to_md_actor=md_actor,valid=o.valid,
   report=function(row,actor)
    if o.defer_ack then
     assert(delivery==nil,'delivery already pending')
     delivery={epoch=row.epoch,sequence=row.sequence,index=row.index}
    end
    if o.expose_actor==true then assert(o.report(row,actor)==true)
    else assert(o.report(row)==true) end
    records=records+1;return true
   end})
  status()
 end
 local function handle(screen,name,value)
  if failed then return end
  local t=now()
  if attach and (phase=='registry_status_epoch' or phase=='registry_status_count' or phase=='queue_preflight' or phase=='queue_init') then
   assert(o.can_attach()==true,'paused attach context lost')
  end
  if started and source_ok()~=true then error('source observation stopped') end
  if hard_stop and t>hard_stop then error('observation drain timeout') end
  if deadline and t>deadline then error('response timeout') end
  if phase=='queue_preflight' and screen==QUEUE and name=='Uninitialized' then
   queue_init_attempted=true
   request(QUEUE,'Initialize',{epoch=o.epoch,capacity=o.capacity},'queue_init');return
  end
  if name=='Faulted' or name=='Refused' or name=='Unavailable' or name=='Uninitialized' then error('MD fault or refusal') end
  if phase=='registry_status_epoch' and screen==REG and name=='Epoch' then
   assert(value==o.epoch,'saved registry epoch mismatch');phase='registry_status_count';return
  end
  if phase=='registry_status_count' and screen==REG and name=='Count' then
   assert(natural(value) and value==o.expected_last,'saved registry count mismatch')
   request(QUEUE,'Status',{},'queue_preflight');return
  end
  if phase=='registry_init' and screen==REG and name=='Initialized' then
   assert(value==o.epoch);baseline_next();return
  end
  if phase=='baseline' and screen==REG and name=='Enrolled' then
   assert(value==index and o.valid(o.baseline[index])==true)
   local key=actor_key(o.baseline[index]);assert(seen[key]);baseline[key]=value
   index=index+1;baseline_next();return
  end
  if phase=='queue_init' and screen==QUEUE and name=='Initialized' then
   assert(value==o.epoch,'queue epoch mismatch')
   if attach then phase='attached_wait_running';deadline=t+o.timeout
   else begin_observation(t) end
   return
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
    assert(o.done({observed=observed,acknowledged=ack,baseline_count=initial_last,
     registry_mode=attach and 'attached' or 'initialized',baseline_known_count=attach and 0 or #o.baseline,
     classification=observed==0 and 'inconclusive_no_events' or 'local_activations_observed',
     birth_confirmed=false,delivery_confirmed=false,coverage='unknown'})==true)
   else phase='ready_front' end
   return
  end
  if phase=='front' and (screen==QUEUE or screen==REG) then
   local ok,reason=driver:event(name,value);assert(ok,reason)
   assert(not failed and phase=='front','state changed during registry response')
   if driver:state()=='idle' then
    phase='waiting';next_poll=t+.1
    if o.defer_ack and name=='Acked' then
     assert(delivery and value==delivery.sequence,'queue ACK mismatch')
     local d=delivery;delivery=nil;notifying=true
     local sent,accepted=pcall(o.queue_acked,d.epoch,d.sequence,d.index)
     assert(sent and accepted==true and not failed and phase=='waiting','queue ACK callback failed')
     local after=now()
     assert(after<deadline and after<hard_stop and source_ok()==true,'queue ACK callback expired')
     notifying=false
    end
    deadline=nil
   end
   if driver:state()=='await_delivery' then
    phase='await_delivery';deadline=t+o.delivery_timeout
    hard_stop=math.max(hard_stop,deadline+o.timeout)
   end
   return
  end
  error('unexpected MD response')
 end
 local api={}
 -- Call only after independently correlating every required client ACK.
 -- This diagnostic owner does not collect clients or authenticate receipts.
 function api:confirm_delivery(epoch,sequence,index)
  if failed or notifying or not o.defer_ack or phase~='await_delivery' then fail('unexpected delivery confirmation');return false end
  local ok,err=pcall(function()
   local t=now()
   assert(t<deadline and t<hard_stop and source_ok()==true,'delivery confirmation expired')
   assert(not failed and phase=='await_delivery' and driver:state()=='await_delivery','state changed before confirmation')
   phase='front';deadline=t+o.timeout
   assert(driver:confirm_delivery(epoch,sequence,index),'delivery confirmation refused')
   assert(not failed and phase=='front' and driver:state()=='ack','state changed during delivery confirmation')
   local after=now()
   assert(after<deadline and after<hard_stop and source_ok()==true,'ACK dispatch expired')
   assert(not failed and phase=='front' and driver:state()=='ack','state changed after delivery confirmation')
  end)
  if not ok then fail(tostring(err));return false end
  return true
 end
 function api:start()
  if phase~='new' then fail('repeated start');return false end
  local ok,err=pcall(function()
   for _,item in ipairs({{REG,'Initialized'},{REG,'Epoch'},{REG,'Count'},{REG,'Uninitialized'},{REG,'Enrolled'},{REG,'Faulted'},{REG,'Refused'},{REG,'Unavailable'},
      {QUEUE,'Initialized'},{QUEUE,'Epoch'},{QUEUE,'Observed'},{QUEUE,'Acknowledged'},
      {QUEUE,'Depth'},{QUEUE,'Inflight'},{QUEUE,'Reason'},{QUEUE,'Healthy'},
      {QUEUE,'Sequence'},{QUEUE,'Actor'},{QUEUE,'Empty'},{QUEUE,'Acked'},
      {QUEUE,'Faulted'},{QUEUE,'Refused'},{QUEUE,'Uninitialized'}}) do
    local screen,name=item[1],item[2]
    o.register(screen..'.'..name,function(_,value)
     local good,why=pcall(handle,screen,name,value);if not good then fail(tostring(why)) end
    end)
   end
   if attach then assert(o.can_attach()==true,'attach requires paused source');request(REG,'Status',{},'registry_status_epoch')
   else request(REG,'Initialize',{epoch=o.epoch},'registry_init') end
  end)
  if not ok then fail(tostring(err));return false end
  return true
 end
 function api:tick()
  if notifying then fail('reentrant queue ACK callback');return false,'failed' end
  if failed or phase=='done' then return false,phase end
  local ok,err=pcall(function()
   local t=now()
   if started and not source_ok() then error('source observation stopped') end
   if hard_stop and t>hard_stop then error('observation drain timeout') end
   if deadline and t>deadline then error('response timeout') end
   if phase=='attached_wait_running' then
    if o.can_observe()==true then begin_observation(t)
    else assert(o.can_attach()==true,'paused attach context lost') end
   elseif attach and (phase=='registry_status_epoch' or phase=='registry_status_count' or phase=='queue_preflight' or phase=='queue_init') then
    assert(o.can_attach()==true,'paused attach context lost')
   elseif phase=='waiting' and t>=next_poll then
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
 if cfg.can_hold_delivery then
  opts.can_hold_delivery=function()
   local current=C.GetSaveFolderPath()
   return current~=nil and current~=ffi.NULL and ffi.string(current):gsub('\\','/'):gsub('/+$','')==cfg.expected_save_path
    and C.IsPlayerValid() and C.IsGamePaused() and cfg.can_hold_delivery()==true
  end
 end
 if opts.attach_saved_registry then
  opts.can_attach=function()
   local current=C.GetSaveFolderPath()
   return current~=nil and current~=ffi.NULL and ffi.string(current):gsub('\\','/'):gsub('/+$','')==cfg.expected_save_path
    and C.IsPlayerValid() and C.IsGamePaused()
  end
 end
 opts.valid=function(actor)
  local id=ffi.new('UniverseID',ConvertIDTo64Bit(actor))
  return C.IsPlayerValid() and C.IsValidComponent(id) and C.IsComponentOperational(id) and C.IsComponentClass(id,'ship')
 end
 return M.new(opts)
end
X4LAN_AUTHORITY_JOB_REGISTRY_HOST=M
return M
