-- Default-off source-only IPC; caller owns local UDP socket and X4 update hook.
-- A SAMPLE is not a TCP receipt or a client X4 apply.
local M={}
local MAX=9007199254740991
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function integer(v)return type(v)=='number' and v==v and v>=1 and v<=MAX and v%1==0 end
local function finite(v)return type(v)=='number' and v==v and v~=-math.huge and v~=math.huge end
local function split(v)local a={};for x in (v..'|'):gmatch('(.-)|')do a[#a+1]=x end;return a end
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 local fixed={};for k,v in pairs(c)do fixed[k]=v end;c=fixed
 assert(token(c.lease) and token(c.attempt) and token(c.epoch) and token(c.generation))
 assert(c.lease~=c.attempt and c.lease~=c.epoch and c.lease~=c.generation and c.attempt~=c.epoch and c.attempt~=c.generation and c.epoch~=c.generation)
 assert(finite(c.timeout) and c.timeout>0 and c.timeout<=120)
 assert(type(c.clock)=='function' and type(c.guard)=='function' and type(c.fault)=='function')
 assert(c.stop==nil or type(c.stop)=='function') -- caller owns sampler, bootstrap and event-router shutdown
 if c.saved_baseline~=nil then
  assert(type(c.saved_baseline)=='table' and integer(c.saved_baseline.limit) and type(c.saved_baseline.guard)=='function')
  c.saved_baseline={limit=c.saved_baseline.limit,guard=c.saved_baseline.guard}
 end
 assert((type(c.net)=='table' or type(c.net)=='userdata') and type(c.net.send)=='function' and type(c.net.receive)=='function')
 local state,busy='new',false;local last,deadline,request,seq,saved_index=nil,nil,nil,0,nil
 local api={}
 local function fail(reason)if state~='failed' then state='failed';pcall(c.fault,reason)end;return false end
 local function check()
  if state=='failed' then return false end
  local before=state;local ok,t=pcall(c.clock)
  if not ok or state~=before or not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return false end
  last=t;local good,v=pcall(c.guard)
  if not good or v~=true or state~=before then return false end
  if state=='register_saved' then
   local ok,allowed=pcall(c.saved_baseline.guard,c.epoch,c.saved_baseline.limit)
   if not ok or allowed~=true or state~=before then return false end
   local yes,again=pcall(c.guard)
   if not yes or again~=true or state~=before then return false end
  end
  local again,u=pcall(c.clock)
  if not again or state~=before or not finite(u) or u<t or (deadline and u>=deadline)then return false end
  last=u;return true
 end
 local function send(fields)
  if not check() then return false end
  local s=table.concat({'S',c.lease,c.attempt,unpack(fields)},'|')
  if #s>768 then return false end
  local before=state;local ok,v=pcall(c.net.send,c.net,s)
  return ok and v==true and state==before and check()
 end
 local function context(kind)return {kind,c.epoch,c.generation}end
 function api:start()
  if busy or state~='new' then return fail('start')end
  busy=true;local ok=pcall(function()assert(check());deadline=last+c.timeout;state='binding';assert(send(context('HELLO')))end)
  busy=false;if not ok then return fail('start')end;return true
 end
 function api:tick()
  if busy or state=='new' or state=='failed' or state=='stopped' then return fail('tick')end
  busy=true
  local ok=pcall(function()
   assert(check());local packet=c.net:receive();assert(check())
   if packet==nil then return end
   assert(type(packet)=='string' and #packet<=768)
   local p=split(packet)
   assert(p[1]=='P' and p[2]==c.lease and p[3]==c.attempt and p[5]==c.epoch and p[6]==c.generation)
   if state=='binding' then
    assert(#p==6 and p[4]=='BOUND');state='ready';assert(send(context('ATTACHED')));deadline=nil
   elseif state=='ready' then
    assert((#p==7 and (p[4]=='PULL' or (p[4]=='STOP' and c.stop))) or (#p==9 and p[4]=='REGISTER_SAVED' and c.saved_baseline))
    assert(p[7]:match('^[1-9]%d*$') and #p[7]<=16)
    local n=tonumber(p[7]);assert(integer(n) and string.format('%.0f',n)==p[7] and n==seq+1)
    request=n;deadline=last+c.timeout
    if p[4]=='STOP' then
     -- stop() must synchronously close the idle bootstrap, sampler and event
     -- router, or return false. Keep the UDP socket owned until X4 cleanup so
     -- the supervisor can still validate its peer after the acknowledgement.
     state='stopping';assert(check())
     local invoked,closed=pcall(c.stop)
     assert(invoked and closed==true and state=='stopping' and check())
     assert(send({'STOPPED',c.epoch,c.generation,string.format('%.0f',request)}))
     seq=request;request=nil;deadline=nil;state='stopped'
    elseif p[4]=='PULL' then state='requested' else
     assert(p[8]:match('^[1-9]%d*$') and #p[8]<=16 and p[9]==string.format('%.0f',c.saved_baseline.limit))
     saved_index=tonumber(p[8]);assert(integer(saved_index) and saved_index<=c.saved_baseline.limit and string.format('%.0f',saved_index)==p[8])
     state='register_saved';assert(check())
    end
   else error('unexpected packet')end
  end)
  busy=false;if not ok then return fail('packet')end;return true
 end
 function api:requested()return state=='requested' end
 function api:saved_request()return state=='register_saved' and saved_index or nil end
 -- The caller must first complete the correlated bootstrap and sampler register.
 function api:saved_registered(index)
  if busy or state~='register_saved' or index~=saved_index then return fail('complete')end
  busy=true;local ok=pcall(function()
   assert(check());assert(send({'SAVED_REGISTERED',c.epoch,c.generation,string.format('%.0f',request),
    string.format('%.0f',saved_index),string.format('%.0f',c.saved_baseline.limit)}))
   seq=request;request=nil;saved_index=nil;deadline=nil;state='ready'
  end)
  busy=false;if not ok then return fail('complete')end;return true
 end
 function api:complete(sample)
  if busy or state~='requested' then return fail('complete')end
  busy=true;local ok=pcall(function()
   assert(check())
   local fields
   if sample==nil then fields={'NO_SAMPLE',c.epoch,c.generation,string.format('%.0f',request)}
   else
    assert(type(sample)=='table' and getmetatable(sample)==nil and sample.version==1 and sample.epoch==c.epoch and sample.generation==c.generation
     and integer(sample.index) and integer(sample.sequence) and type(sample.sector_macro)=='string' and #sample.sector_macro<=128
     and sample.sector_macro:match('^[A-Za-z0-9_]+$') and finite(sample.source_time) and sample.source_time>=0 and sample.source_time<=1e12)
    for _,k in ipairs({'x','y','z'})do assert(finite(sample[k]) and math.abs(sample[k])<=1e7)end
    local v=sample.velocity
    if v~=nil then assert(type(v)=='table' and getmetatable(v)==nil);for _,k in ipairs({'x','y','z'})do assert(finite(v[k]) and math.abs(v[k])<=5000)end end
    fields={'SAMPLE',c.epoch,c.generation,string.format('%.0f',request),string.format('%.0f',sample.index),
     string.format('%.0f',sample.sequence),sample.sector_macro,string.format('%.17g',sample.source_time)}
    for _,k in ipairs({'x','y','z'})do fields[#fields+1]=string.format('%.17g',sample[k])end
    for _,k in ipairs({'x','y','z'})do fields[#fields+1]=v and string.format('%.17g',v[k]) or '-'end
   end
   assert(send(fields));seq=request;request=nil;deadline=nil;state='ready'
  end)
  busy=false;if not ok then return fail('complete')end;return true
 end
 function api:state()return state end
 return api
end
X4LAN_AUTHORITY_SOURCE_MOTION_IPC=M
return M
