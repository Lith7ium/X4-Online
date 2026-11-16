-- Default-off bounded orchestration experiment. No X4, networking or hooks.
-- Binding/writer factories must independently enforce their real local guards.
local M={}
local MAX=9007199254740991
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function integer(n)return finite(n) and n>=1 and n<=MAX and n%1==0 end
local function token(v,n)return type(v)=='string' and #v==n and v:match('^[0-9a-f]+$')~=nil end
local function name(v)return type(v)=='string' and #v>0 and #v<=128 and v:match('^[A-Za-z0-9_]+$')~=nil end
local function vector(v,limit)
 if type(v)~='table' or getmetatable(v)~=nil then return false end
 for k in pairs(v)do if k~='x' and k~='y' and k~='z' then return false end end
 return finite(v.x) and finite(v.y) and finite(v.z) and math.abs(v.x)<=limit and math.abs(v.y)<=limit and math.abs(v.z)<=limit
end
local function valid(s,c)
 if type(s)~='table' or getmetatable(s)~=nil then return false end
 local keys={version=true,epoch=true,generation=true,index=true,sequence=true,sector_macro=true,source_time=true,
  x=true,y=true,z=true,velocity=true,digest=true,request=true}
 for k in pairs(s)do if not keys[k] then return false end end
 return s.version==1 and s.epoch==c.epoch and s.generation==c.generation and s.index==c.index and
  s.sector_macro==c.sector_macro and integer(s.sequence) and finite(s.source_time) and s.source_time>=0 and s.source_time<=1e12 and
  finite(s.x) and finite(s.y) and finite(s.z) and math.abs(s.x)<=1e7 and math.abs(s.y)<=1e7 and math.abs(s.z)<=1e7 and
  (s.velocity==nil or vector(s.velocity,5000)) and token(s.digest,64) and token(s.request,32)
end
local function copy(s)
 local t={};for k,v in pairs(s)do if k~='velocity' then t[k]=v end end
 if s.velocity then t.velocity={x=s.velocity.x,y=s.velocity.y,z=s.velocity.z}end
 return t
end
local function same(a,b,c)
 if not valid(a,c) then return false end
 for k,v in pairs(b)do
  if k~='velocity' and (type(a[k])~=type(v) or a[k]~=v) then return false end
 end
 if b.velocity then return a.velocity and a.velocity.x==b.velocity.x and a.velocity.y==b.velocity.y and a.velocity.z==b.velocity.z end
 return a.velocity==nil
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 assert(token(c.epoch,32) and token(c.generation,32) and c.epoch~=c.generation and integer(c.index) and name(c.sector_macro))
 assert(integer(c.max_samples) and c.max_samples<=8 and finite(c.timeout) and c.timeout>1 and c.timeout<=30 and
  finite(c.max_age) and c.max_age>1 and c.max_age<=30)
 for _,k in ipairs({'clock','guard','binding_factory','writer_factory','complete','fault'})do assert(type(c[k])=='function',k)end
 local state,busy='new',false;local now,deadline,arrival,pending,binder,writer,staged=nil,nil,nil,nil,nil,nil,nil
 local last_sequence,last_source,actor,sector,zone=0,nil,nil,nil,nil
 local requested={};local delivered,uncertain=false,false;local api={}
 local function fail(reason)
  if state~='failed' then state='failed';pcall(c.fault,reason,uncertain)end
  return false
 end
 local function check()
  if state=='failed' then return false end
  local before=state;local ok,t=pcall(c.clock)
  if not ok or not finite(t) or t<0 or (now and t<now) or (deadline and t>=deadline) or
   (arrival and (t<arrival or t-arrival>c.max_age)) or state~=before then return false end
  now=t;local good,v=pcall(c.guard)
  if not good or v~=true or state~=before then return false end
  local again,u=pcall(c.clock)
  if not again or not finite(u) or u<t or (deadline and u>=deadline) or
   (arrival and (u<arrival or u-arrival>c.max_age)) or state~=before then return false end
  now=u;return true
 end
 function api:start()
  if busy or state~='new' then return fail('start')end
  busy=true;local ok=pcall(function()
   assert(check());local options={epoch=c.epoch,generation=c.generation,index=c.index,sector_macro=c.sector_macro,
    capture_binding=function(a,s,z,i,n)
     if state~='binding' or not pending or staged or i~=c.index or n~=pending.sequence or
      type(a)~='string' or type(s)~='string' or type(z)~='string' or
      not a:match('^[1-9]%d*$') or not s:match('^[1-9]%d*$') or not z:match('^[1-9]%d*$') then return false end
     staged={actor=a,sector=s,zone=z};return true
    end,
    complete=function(v)
     if state~='binding' or not pending or delivered or type(v)~='table' or v.epoch~=c.epoch or
      v.generation~=c.generation or v.index~=c.index or v.sequence~=pending.sequence or v.sector_macro~=c.sector_macro then return false end
     delivered=true;return true
    end}
   binder=assert(c.binding_factory(options));assert(type(binder.begin)=='function' and type(binder.event)=='function' and type(binder.tick)=='function')
   assert(state=='new' and check());state='ready'
  end);busy=false;if not ok then return fail('start')end;return true
 end
 function api:submit(sample)
  if busy or state~='ready' then return fail('submit')end
  busy=true;local ok=pcall(function()
   assert(valid(sample,c) and sample.sequence==last_sequence+1 and (not last_source or sample.source_time>last_source) and
    (last_sequence~=0 or sample.velocity==nil) and not requested[sample.request] and check())
   pending=copy(sample);arrival=now;deadline=now+c.timeout;requested[pending.request]=true;staged=nil;delivered=false;uncertain=false
   state='binding';assert(binder:begin({epoch=c.epoch,generation=c.generation,index=c.index,sequence=pending.sequence,
    sector_macro=c.sector_macro},arrival)==true and state=='binding' and check())
  end);busy=false;if not ok then return fail('submit')end;return true
 end
 function api:binding_event(value)
  if busy or state~='binding' or not pending then return fail('binding_event')end
  busy=true;local ok=pcall(function()
   assert(check() and binder:event(value)==true and state=='binding' and delivered and staged and check())
   if actor then assert(staged.actor==actor and staged.sector==sector and staged.zone==zone)end
   actor,sector,zone=staged.actor,staged.sector,staged.zone
   state='writing';writer=assert(c.writer_factory({guard=function()return state=='writing' and check() and state=='writing'end,
    fault=function()fail('writer')end}))
   assert(state=='writing' and type(writer.begin)=='function' and type(writer.event)=='function' and type(writer.tick)=='function' and type(writer.state)=='function' and check())
   assert(writer:begin({request=pending.request,epoch=c.epoch,generation=c.generation,digest=pending.digest,index=c.index,
    sequence=pending.sequence,sector_macro=c.sector_macro,actor_key=actor,sector_key=sector,zone_key=zone,
    target={x=pending.x,y=pending.y,z=pending.z}})==true and state=='writing' and check())
  end);busy=false;if not ok then return fail('binding_event')end;return true
 end
 function api:writer_event(value)
  if busy or state~='writing' or not writer then return fail('writer_event')end
  busy=true;local ok=pcall(function()
   assert(check());uncertain=true -- writer may enter native write before reporting an error
   assert(writer:event(value)==true and state=='writing' and check())
  end);busy=false;if not ok then return fail('writer_event')end;return true
 end
 function api:tick()
  if busy or (state~='ready' and state~='binding' and state~='writing') then return fail('tick')end
  busy=true;local ok=pcall(function()
   assert(check())
   if state=='binding' then assert(binder:tick()==true and state=='binding' and check())
   elseif state=='writing' then
    assert(writer:tick()==true and state=='writing' and check())
    local writer_state=writer:state();assert(state=='writing' and check())
    if writer_state=='done' then
     assert(check());local result=copy(pending);local expected=copy(pending)
     assert(c.complete(result)==true and state=='writing' and check() and same(result,expected,c))
     last_sequence=pending.sequence;last_source=pending.source_time;pending=nil;arrival=nil;deadline=nil;staged=nil;uncertain=false
     state=last_sequence==c.max_samples and 'done' or 'ready'
    end
   end
  end);busy=false;if not ok then return fail('tick')end;return true
 end
 function api:state()return state end
 function api:outcome_uncertain()return uncertain end
 return api
end
return M
