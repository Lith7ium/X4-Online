-- Default-off local client authority adapter. Existing participant onUpdate
-- and one descriptor event route own this object; no server write or handover.
local M={}
local function equal(left,right)
 if type(left)~=type(right) then return false end
 if type(left)~='table' then return left==right end
 if getmetatable(left)~=nil or getmetatable(right)~=nil then return false end
 for key,value in pairs(left)do if right[key]==nil or not equal(value,right[key]) then return false end end
 for key in pairs(right)do if left[key]==nil then return false end end
 return true
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 for _,k in ipairs({'guard','grant','register','ipc_factory','reader_factory','fault'})do assert(type(c[k])=='function',k)end
 if c.fixture_slot~=nil then
  assert((c.fixture_slot==1 or c.fixture_slot==2) and c.index==c.fixture_slot+2 and
   c.baseline==4 and c.include_orientation==true)
 else
  assert(c.index==1318 and c.baseline==10054)
 end
 assert(c.audit==nil or type(c.audit)=='function')
 assert(c.cache_evidence==nil or type(c.cache_evidence)=='function')
 assert(c.latest_cache==nil or type(c.latest_cache)=='boolean')
 if c.latest_cache then assert(c.fixture_slot~=nil and type(c.latest_factory)=='function')end
 assert(c.freeze_drain==nil or type(c.freeze_drain)=='boolean')
 if c.freeze_drain then assert(c.latest_cache==true and type(c.barrier_factory)=='function')end
 local state,busy='new',false;local ipc,reader,staged,registered,latest=nil,nil,nil,false,nil
 local barrier,scheduling=nil,true
 local api={}
 local function fail(reason)if state~='failed' then state='failed';pcall(c.fault,reason)end;return false end
 local function check()
  if state=='failed' then return false end
  local old=state;local ok,v=pcall(c.guard);if not ok or v~=true or state~=old then return false end
  local yes,g=pcall(c.grant,c.epoch,c.generation,c.index);if not yes or g~=true or state~=old then return false end
  local again,w=pcall(c.guard);return again and w==true and state==old
 end
 function api:start()
  if busy or state~='new' then return fail('start')end
  busy=true;local ok=pcall(function()
   assert(check());ipc=assert(c.ipc_factory({guard=check,fault=function()fail('ipc')end}))
   assert(state=='new' and check());assert(c.register(function(_,v)api:event(v)end)==true and state=='new' and check())
   assert(ipc:start() and state=='new' and check());state='ready'
  end);busy=false;if not ok then return fail('start')end;return true
 end
 function api:tick()
  if busy or state~='ready' then return fail('tick')end
  busy=true;local ok=pcall(function()
   assert(check() and ipc:tick() and state=='ready' and check())
   local index=ipc:saved_request()
   if index~=nil then
    assert(index==c.index and not registered and check())
    if not reader then
     reader=assert(c.reader_factory({guard=check,authority=function(e,g,i)
      return e==c.epoch and g==c.generation and i==c.index and check()
     end,stage_sample=function(v)
      if state~='ready' or staged or (not c.latest_cache and not ipc:requested()) or not check() then return false end
      staged=v;return true
     end,fault=function()fail('reader')end}))
     assert(state=='ready' and check() and reader:start() and check())
    else assert(reader:state()=='bootstrapping' or reader:state()=='sampling')end
   end
   if reader then
    if reader:state()=='bootstrapping' or (not c.latest_cache and ipc:requested()) then
     assert(reader:tick() and state=='ready' and check())
    end
    if ipc:saved_request()~=nil and reader:state()=='sampling' then
     assert(ipc:saved_request()==c.index and not registered and ipc:saved_registered(c.index) and check());registered=true
    end
    if c.latest_cache and registered then
     if not latest then
      latest=assert(c.latest_factory({guard=check,inspect=function()return reader:cache_context()end,
       authority=function()return check()end,validate_capture=function(sample)
        return staged~=nil and equal(sample,staged) and check()
       end,quiescent=function()
        return (ipc:state()=='ready' or (c.freeze_drain and ipc:state()=='freeze_requested')) and
         not staged and reader:state()=='sampling' and reader:expected_request()==nil
       end,reset_sampler=function()return reader:reset_sampling_baseline()end}))
     end
     if c.freeze_drain and not barrier then
      local function quiet()
       local phase=ipc:state()
       return (phase=='freeze_requested' or phase=='resume_requested' or phase=='frozen' or phase=='ready') and
        ipc:queue_empty() and not staged and reader:state()=='sampling' and reader:expected_request()==nil
      end
      barrier=assert(c.barrier_factory({guard=check,stop_scheduling=function()scheduling=false;return true end,
       quiescent=quiet,reset_cache=function()return latest:pause()end,resume_cache=function()return latest:resume()end,
       start_scheduling=function()scheduling=true;return true end,send_ack=function(kind,id)
        if kind=='freeze' then return ipc:freeze_complete(id)end
        if kind=='resume' then return ipc:resume_complete(id)end
        return false
       end}))
     end
     if c.freeze_drain and ipc:freeze_request()~=nil then
      if barrier:state()=='running' then assert(barrier:freeze(ipc:freeze_request()))end
      if reader:expected_request()~=nil then assert(reader:tick() and check())end
      assert(barrier:tick() and state=='ready' and check())
     elseif c.freeze_drain and ipc:resume_request()~=nil then
      assert(barrier:resume(ipc:resume_request()) and state=='ready' and check())
     elseif c.freeze_drain and ipc:state()=='frozen' then
      assert(barrier:state()=='frozen' and not scheduling)
     elseif ipc:requested() then
      local envelope,status=latest:pull()
      assert(envelope~=false and (status=='sample' or status=='empty') and check())
      if envelope and c.audit then
       local sample=envelope.sample
       local ok,a=pcall(c.audit,sample.index,sample.sequence,sample.sector_macro,sample.source_time,sample.x,sample.y,sample.z)
       assert(ok and a==true and state=='ready' and check())
      end
      assert(ipc:complete(envelope and envelope.sample or nil) and check())
      if envelope and envelope.capture_sequence>envelope.delivery_sequence and envelope.sample.velocity and c.cache_evidence then
       assert(c.cache_evidence(envelope.capture_sequence,envelope.delivery_sequence)==true and check())
      end
     end
     if scheduling then assert(reader:tick() and state=='ready' and check())end
    elseif ipc:requested() then
     assert(registered and reader:state()=='sampling' and not staged and check())
     if reader:expected_request()==nil then assert(ipc:complete(nil) and check())end
    end
   else assert(not ipc:requested())end
  end);busy=false;if not ok then return fail('tick')end;return true
 end
 function api:event(value)
  if busy or state~='ready' or not reader then return fail('event')end
  busy=true;local ok=pcall(function()
   assert(check() and not staged and reader:event(value)==true and state=='ready' and check())
   if staged then
    if c.latest_cache then
     assert(registered and latest and latest:capture(staged)==true and state=='ready' and check())
     staged=nil
    else
    assert(registered and ipc:requested() and check());local sample=staged;staged=nil
    if c.audit then
     local ok,a=pcall(c.audit,sample.index,sample.sequence,sample.sector_macro,sample.source_time,sample.x,sample.y,sample.z)
     assert(ok and a==true and state=='ready' and check())
    end
    assert(ipc:complete(sample) and state=='ready' and check())
    end
   end
  end);busy=false;if not ok then return fail('event')end;return true
 end
 -- A pause is safe only between protocol operations. The owner must also
 -- check the socket for queued packets before and during the pause.
 function api:quiescent()
  return not busy and state=='ready' and ipc and
   ((c.freeze_drain and ipc:state()=='frozen') or (not c.freeze_drain and ipc:state()=='ready')) and not staged and
   (not reader or (reader:state()=='sampling' and reader:expected_request()==nil))
 end
 function api:after_resume()
  if not c.latest_cache then return true end
  if busy or state~='ready' then return fail('resume')end
  busy=true;local ok=pcall(function()
   assert(check())
   if latest then assert(latest:pause() and latest:resume() and state=='ready' and check())end
  end)
  busy=false;if not ok then return fail('resume')end;return true
 end
 function api:state()return state end
 return api
end
function M.new_x4(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(type(o.reader)=='table' and type(o.reader.new_x4)=='function' and type(o.ipc)=='table' and type(o.ipc.new)=='function')
 assert(type(RegisterEvent)=='function' and type(GetCurRealTime)=='function')
 assert(o.event_register==nil or type(o.event_register)=='function')
 local c={};for k,v in pairs(o)do c[k]=v end
 local reader_new,ipc_new=c.reader.new_x4,c.ipc.new
 c.register=function(fn)
  if c.event_register then return c.event_register(fn)==true end
  return RegisterEvent('X4AuthorityJobDescriptorProbe.Result',fn)~=false
 end
 c.ipc_factory=function(x)
  x.enabled=true;x.lease=c.lease;x.attempt=c.attempt;x.epoch=c.epoch;x.generation=c.generation;x.timeout=c.timeout
  x.clock=GetCurRealTime;x.net=c.net;x.freeze_drain=c.freeze_drain;x.saved_baseline={limit=c.baseline,guard=function(e,n)
   return e==c.epoch and n==c.baseline and x.guard()==true
  end};return ipc_new(x)
 end
 c.reader_factory=function(x)
  x.enabled=true;x.epoch=c.epoch;x.generation=c.generation;x.index=c.index;x.baseline=c.baseline;x.sector=c.sector
  x.bootstrap_nonce=c.bootstrap_nonce;x.sampler_nonce=c.sampler_nonce;x.timeout=c.timeout;x.interval=c.interval
  x.include_orientation=c.include_orientation
  x.fixture_slot=c.fixture_slot
  x.latest_cache=c.latest_cache
  x.bootstrap=c.bootstrap;x.sampler=c.sampler;x.descriptor=c.descriptor;x.resolve=c.resolve;x.expected_save_path=c.expected_save_path
  return reader_new(x)
 end
 if c.freeze_drain then
  assert(type(c.barrier_module)=='table' and type(c.barrier_module.new)=='function')
  c.barrier_factory=function(x)
   x.enabled=true;x.clock=GetCurRealTime;x.timeout=c.timeout
   return c.barrier_module.new(x)
  end
 end
 if c.latest_cache then
  assert(type(c.cache_module)=='table' and type(c.cache_module.new)=='function' and c.fixture_slot~=nil)
  if type(DebugError)=='function' then
   local reported=false
   c.cache_evidence=function(capture,delivery)
    if not reported then
     DebugError('[X4LAN] AUTH_FIXTURE_PLAYER_LATEST SKIPPED '..capture..' '..delivery)
     reported=true
    end
    return true
   end
  end
  c.latest_factory=function(x)
   return c.cache_module.new({enabled=true,grant={index=c.index,epoch=c.epoch,generation=c.generation,
    source=c.bootstrap_nonce,frame=c.sampler_nonce,sector=c.sector},max_age=1,clock=GetCurRealTime,
    guard=x.guard,authority=x.authority,inspect=x.inspect,validate_capture=x.validate_capture,
    quiescent=x.quiescent,reset_sampler=x.reset_sampler})
  end
 end
 return M.new(c)
end
X4LAN_CLIENT_AUTHORITY_MOTION_SESSION=M
return M
