-- Default-off local client authority adapter. Existing participant onUpdate
-- and one descriptor event route own this object; no server write or handover.
local M={}
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 for _,k in ipairs({'guard','grant','register','ipc_factory','reader_factory','fault'})do assert(type(c[k])=='function',k)end
 assert(c.index==1318 and c.baseline==10054)
 assert(c.audit==nil or type(c.audit)=='function')
 local state,busy='new',false;local ipc,reader,staged,registered=nil,nil,nil,false
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
      if state~='ready' or staged or not ipc:requested() or not check() then return false end
      staged=v;return true
     end,fault=function()fail('reader')end}))
     assert(state=='ready' and check() and reader:start() and check())
    else assert(reader:state()=='bootstrapping' or reader:state()=='sampling')end
   end
   if reader then
    if reader:state()=='bootstrapping' or ipc:requested() then assert(reader:tick() and state=='ready' and check())end
    if ipc:saved_request()~=nil and reader:state()=='sampling' then
     assert(ipc:saved_request()==c.index and not registered and ipc:saved_registered(c.index) and check());registered=true
    end
    if ipc:requested() then
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
    assert(registered and ipc:requested() and check());local sample=staged;staged=nil
    if c.audit then
     local ok,a=pcall(c.audit,sample.index,sample.sequence,sample.sector_macro,sample.source_time,sample.x,sample.y,sample.z)
     assert(ok and a==true and state=='ready' and check())
    end
    assert(ipc:complete(sample) and state=='ready' and check())
   end
  end);busy=false;if not ok then return fail('event')end;return true
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
  x.clock=GetCurRealTime;x.net=c.net;x.saved_baseline={limit=c.baseline,guard=function(e,n)
   return e==c.epoch and n==c.baseline and x.guard()==true
  end};return ipc_new(x)
 end
 c.reader_factory=function(x)
  x.enabled=true;x.epoch=c.epoch;x.generation=c.generation;x.index=c.index;x.baseline=c.baseline;x.sector=c.sector
  x.bootstrap_nonce=c.bootstrap_nonce;x.sampler_nonce=c.sampler_nonce;x.timeout=c.timeout;x.interval=c.interval
  x.include_orientation=c.include_orientation
  x.bootstrap=c.bootstrap;x.sampler=c.sampler;x.descriptor=c.descriptor;x.resolve=c.resolve;x.expected_save_path=c.expected_save_path
  return reader_new(x)
 end
 return M.new(c)
end
X4LAN_CLIENT_AUTHORITY_MOTION_SESSION=M
return M
