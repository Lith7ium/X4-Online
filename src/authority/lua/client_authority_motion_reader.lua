-- Explicit one-client test authority, read-only and actor-local. The existing
-- X4 owner must drive tick/event and exclusively route descriptor responses.
-- An external grant/checkpoint fence is a caller assertion, not HA authority.
local M={}
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function finite(v)return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge end
local function name(v)return type(v)=='string' and #v>0 and #v<=128 and v:match('^[A-Za-z0-9_]+$')~=nil end
local function vector(v,axes,limit)
 if type(v)~='table' then return false end
 for _,axis in ipairs(axes)do if not finite(v[axis]) or math.abs(v[axis])>limit then return false end end
 return true
end
local function clone(v)
 if type(v)~='table' then return v end
 local result={};for k,value in pairs(v)do result[k]=clone(value)end;return result
end
local function unchanged(value,expected)
 if type(value)~=type(expected) then return false end
 if type(value)~='table' then return value==expected end
 if getmetatable(value)~=nil then return false end
 for k in pairs(value)do if expected[k]==nil then return false end end
 for k,v in pairs(expected)do if not unchanged(value[k],v) then return false end end
 return true
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 assert(token(c.epoch) and token(c.generation) and token(c.bootstrap_nonce) and token(c.sampler_nonce))
 assert(c.epoch~=c.generation and c.bootstrap_nonce~=c.sampler_nonce and c.bootstrap_nonce:sub(1,16)~=c.sampler_nonce:sub(1,16))
 assert(c.index==1318 and c.baseline==10054 and c.sector=='cluster_115_sector001_macro')
 assert(c.include_orientation==nil or type(c.include_orientation)=='boolean')
 for _,k in ipairs({'guard','authority','bootstrap_factory','sampler_factory','stage_sample','fault'})do assert(type(c[k])=='function',k)end
 local state,busy='new',false;local bootstrap,sampler,staged,actor,last_sequence,last_time=nil,nil,nil,nil,0,nil
 local api={}
 local function fail(reason)if state~='failed' then state='failed';pcall(c.fault,reason)end;return false end
 local function check()
  if state=='failed' or state=='closed' then return false end
  local before=state;local ok,g=pcall(c.guard)
  if not ok or g~=true or state~=before then return false end
  local ok2,grant=pcall(c.authority,c.epoch,c.generation,c.index)
  if not ok2 or grant~=true or state~=before then return false end
  local ok3,again=pcall(c.guard)
  return ok3 and again==true and state==before
 end
 local function expect(v)
  return type(v)=='table' and v.version==(c.include_orientation and 2 or 1) and v.epoch==c.epoch and v.generation==c.generation and
   v.index==c.index and type(v.sequence)=='number' and v.sequence==last_sequence+1 and
   v.sector_macro==c.sector and name(v.sector_macro) and finite(v.source_time) and v.source_time>=0 and
   (not last_time or v.source_time>last_time) and (last_sequence~=0 or v.velocity==nil) and
   finite(v.x) and finite(v.y) and finite(v.z) and math.abs(v.x)<=1e7 and math.abs(v.y)<=1e7 and math.abs(v.z)<=1e7 and
   (v.velocity==nil or vector(v.velocity,{'x','y','z'},5000)) and
   (not c.include_orientation or (vector(v.orientation,{'yaw','pitch','roll'},2*math.pi) and
    (v.velocity==nil)==(v.angular_rate==nil) and
    (v.angular_rate==nil or vector(v.angular_rate,{'yaw','pitch','roll'},2*math.pi))))
 end
 function api:start()
  if busy or state~='new' then return fail('start')end
  busy=true;local ok=pcall(function()
   assert(check())
   bootstrap=assert(c.bootstrap_factory({epoch=c.epoch,baseline=c.baseline,nonce=c.bootstrap_nonce,
    complete=function(index,a,sector)
     if state~='bootstrapping' or staged or index~=c.index or sector~=c.sector or a==nil or not check() then return false end
     staged={actor=a};return true
    end}))
   sampler=assert(c.sampler_factory({epoch=c.epoch,generation=c.generation,nonce=c.sampler_nonce,include_orientation=c.include_orientation,
    saved_baseline_limit=c.baseline,saved_baseline_guard=function(row,a)
     return state=='sampling' and row.epoch==c.epoch and row.index==c.index and row.classification=='saved_baseline' and
      actor~=nil and actor==a and check()
    end,fault=function()fail('sampler')end}))
   assert(state=='new' and check());state='bootstrapping'
   assert(bootstrap:begin(c.index)==true and state=='bootstrapping' and check())
  end);busy=false;if not ok then return fail('start')end;return true
 end
 function api:tick()
  if busy or (state~='bootstrapping' and state~='sampling') then return fail('tick')end
  busy=true;local ok=pcall(function()
   assert(check())
   if state=='bootstrapping' then assert(bootstrap:tick()==true and state=='bootstrapping' and check())
   else assert(sampler:tick()==true and state=='sampling' and check())end
  end);busy=false;if not ok then return fail('tick')end;return true
 end
 function api:event(value)
  if busy or (state~='bootstrapping' and state~='sampling') then return fail('event')end
  busy=true;local ok=pcall(function()
   assert(check() and type(value)=='string')
   local id=value:match('^([0-9a-f]+)|');assert(id)
   if state=='bootstrapping' then
    assert(id==bootstrap:expected_request() and not staged and bootstrap:event(value)==true and bootstrap:state()=='idle' and staged and check())
    actor=staged.actor;staged=nil;state='sampling'
    assert(sampler:register({epoch=c.epoch,index=c.index,classification='saved_baseline'},actor)==true and state=='sampling' and check())
   else
    assert(id==sampler:expected_request())
    local accepted,v=sampler:event(value);assert(accepted==true and state=='sampling' and check())
    if v~=nil then
     assert(expect(v))
     local expected={version=v.version,epoch=v.epoch,generation=v.generation,index=v.index,sequence=v.sequence,sector_macro=v.sector_macro,
      source_time=v.source_time,x=v.x,y=v.y,z=v.z}
     if v.velocity then expected.velocity={x=v.velocity.x,y=v.velocity.y,z=v.velocity.z} end
     if c.include_orientation then
      expected.orientation={yaw=v.orientation.yaw,pitch=v.orientation.pitch,roll=v.orientation.roll}
      if v.angular_rate then expected.angular_rate={yaw=v.angular_rate.yaw,pitch=v.angular_rate.pitch,roll=v.angular_rate.roll} end
     end
     local copy=clone(expected)
     assert(unchanged(v,expected) and unchanged(copy,expected))
     -- This callback is provisional until event() returns true. The owner
     -- must stage it locally and publish only after that successful return.
     local accepted=c.stage_sample(copy);assert(accepted==true and state=='sampling' and unchanged(v,expected) and unchanged(copy,expected))
     assert(check() and unchanged(v,expected) and unchanged(copy,expected))
     last_sequence=expected.sequence;last_time=expected.source_time
    end
   end
  end);busy=false;if not ok then return fail('event')end;return true
 end
 function api:expected_request()
  if state=='bootstrapping' then return bootstrap:expected_request()end
  if state=='sampling' then return sampler:expected_request()end
  return nil
 end
 function api:state()return state end
 return api
end
function M.new_x4(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(type(o.bootstrap)=='table' and type(o.bootstrap.new_x4)=='function' and type(o.sampler)=='table' and type(o.sampler.new_x4)=='function')
 assert(type(o.descriptor)=='table' and type(o.resolve)=='table' and type(o.expected_save_path)=='string')
 local c={};for k,v in pairs(o)do c[k]=v end
 local b,s=c.bootstrap.new_x4,c.sampler.new_x4
 c.bootstrap_factory=function(x)
  x.enabled=true;x.timeout=c.timeout;x.guard=c.guard;x.baseline_guard=function(e,n)
   return e==c.epoch and n==c.baseline and c.authority(c.epoch,c.generation,c.index)==true and c.guard()==true
  end
  x.expected_save_path=c.expected_save_path;x.resolve=c.resolve;return b(x)
 end
 c.sampler_factory=function(x)
  x.enabled=true;x.max_tracks=1;x.scan_budget=1;x.interval=c.interval;x.timeout=c.timeout;x.min_dt=.02;x.max_dt=1
  x.include_orientation=c.include_orientation
  x.descriptor=c.descriptor;x.resolve=c.resolve;x.expected_save_path=c.expected_save_path;x.guard=c.guard
  x.binding_guard=function()return false end;return s(x)
 end
 return M.new(c)
end
X4LAN_CLIENT_AUTHORITY_MOTION_READER=M
return M
