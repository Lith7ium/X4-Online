-- Default-off local motion bind IPC; one existing UI owner drives start/tick.
-- No setter, actor handle on wire, independent update hook or TCP reader.
local M={};local MAX=9007199254740991
local owners=setmetatable({},{__mode='k'});local registered=false
local function token(v,n)return type(v)=='string' and #v==n and v:match('^[0-9a-f]+$')~=nil end
local function integer(v)return type(v)=='number' and v==v and v>=1 and v<=MAX and v%1==0 end
local function natural(v)
 if type(v)~='string' or #v>16 or not v:match('^[1-9]%d*$') then return nil end
 local n=tonumber(v);if not integer(n) or string.format('%.0f',n)~=v then return nil end;return n
end
local function number(v,lo,hi)
 if type(v)~='string' or #v<1 or #v>32 or not v:match('^[%d%.%+%-eE]+$') then return nil end
 local n=tonumber(v);if not n or n~=n or n<lo or n>hi then return nil end;return n
end
local function name(v)return type(v)=='string' and #v>=1 and #v<=128 and v:match('^[A-Za-z0-9_]+$')~=nil end
local function split(v)local p={};for s in (v..'|'):gmatch('(.-)|')do p[#p+1]=s end;return p end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 for _,k in ipairs({'lease','attempt','epoch','generation','nonce'})do assert(token(c[k],32),k)end
 assert(c.lease~=c.attempt and c.lease~=c.epoch and c.lease~=c.generation and c.attempt~=c.epoch and c.attempt~=c.generation and c.epoch~=c.generation and c.nonce~=c.lease and c.nonce~=c.attempt and c.nonce~=c.epoch and c.nonce~=c.generation)
 assert(type(c.timeout)=='number' and c.timeout>0 and c.timeout<=30 and type(c.max_age)=='number' and c.max_age>0 and c.max_age<=30)
 assert(integer(c.max_tracks) and c.max_tracks<=100000)
 assert(type(c.buffer)=='table' and type(c.buffer.new)=='function')
 local new_buffer=c.buffer.new
 for _,k in ipairs({'clock','guard','register','factory','fault'})do assert(type(c[k])=='function',k)end
 assert(c.audit==nil or type(c.audit)=='function')
 assert((type(c.net)=='table' or type(c.net)=='userdata') and type(c.net.send)=='function' and type(c.net.receive)=='function')
 assert(not owners[c.net],'motion socket already owned');owners[c.net]=true
 local state,busy='new',false;local last,pending,deadline,delivered=nil,nil,nil,nil
 local tracks,track_count={},0;local api={}
 local function fail(reason)if state~='failed' then state='failed';pcall(c.fault,reason)end;return false end
 local function check()
  if state=='failed' then return false end
  local old=state;local ok,t=pcall(c.clock)
  if not ok or state~=old or type(t)~='number' or t~=t or t<0 or t==math.huge or (last and t<last) or (deadline and t>=deadline) then return false end
  last=t;local good,g=pcall(c.guard);if not good or g~=true or state~=old then return false end
  local yes,u=pcall(c.clock)
  if not yes or state~=old or type(u)~='number' or u~=u or u<t or u==math.huge or (deadline and u>=deadline) then return false end
  last=u;return true
 end
 local function send(text)
  if #text>768 or not check() then return false end
  local old=state;local ok,v=pcall(c.net.send,c.net,text)
  return ok and v==true and state==old and check()
 end
 local function reply(kind,identity)
  local p={'R',c.lease,c.attempt,kind}
  if identity then for _,v in ipairs(identity)do p[#p+1]=v end
  else p[#p+1]=c.epoch;p[#p+1]=c.generation end
  return table.concat(p,'|')
 end
 function api:start()
  if busy or state~='new' then return fail('start')end
  busy=true;local ok=pcall(function()
   assert(check());assert(c.register(function(_,v)api:event(v)end)==true and state=='new')
   state='ready';assert(send(reply('READY')))
  end);busy=false;if not ok then return fail('start')end;return true
 end
 local function accept(raw)
  if type(raw)~='string' or #raw>768 then return false end
  local p=split(raw)
  if #p~=18 or p[1]~='M' or p[2]~=c.lease or p[3]~=c.attempt or p[4]~='BIND' or
     not token(p[5],32) or p[6]~=c.epoch or p[7]~=c.generation or not name(p[10]) or not token(p[11],64) then return false end
  local index,seq=natural(p[8]),natural(p[9]);if not index or not seq then return false end
  local t=number(p[12],0,1e12);local x,y,z=number(p[13],-1e7,1e7),number(p[14],-1e7,1e7),number(p[15],-1e7,1e7)
  if not t or not x or not y or not z then return false end
  local rate
  if p[16]=='-' and p[17]=='-' and p[18]=='-' then rate=nil
  else
   local vx,vy,vz=number(p[16],-5000,5000),number(p[17],-5000,5000),number(p[18],-5000,5000)
   if not vx or not vy or not vz then return false end;rate={vx,vy,vz}
  end
  if not check() then return false end
  local arrival=last
  local entry=tracks[index]
  if entry and entry.sector~=p[10] then return false end
  if not entry then
   if track_count>=c.max_tracks then return false end
   track_count=track_count+1
   local nonce=c.nonce -- full 128-bit owner nonce; binding adds index and request counter
   local binding=assert(c.factory({epoch=c.epoch,generation=c.generation,index=index,sector_macro=p[10],nonce=nonce,
    timeout=c.timeout,max_age=c.max_age,complete=function(result)
     if state~='pending' or delivered or not pending or type(result)~='table' or result.epoch~=c.epoch or
        result.generation~=c.generation or result.index~=pending.index or result.sequence~=pending.sequence or result.sector_macro~=pending.sector then return false end
     delivered=true;return true
    end}))
   if state~='ready' or not check() then return false end
   local buffer=assert(new_buffer({dimensions=3,hold_only=true}))
   if type(buffer)~='table' or type(buffer.push)~='function' or state~='ready' or not check() then return false end
   entry={sector=p[10],binding=binding,buffer=buffer};tracks[index]=entry
  end
  pending={identity={p[5],p[6],p[7],p[8],p[9],p[10],p[11]},index=index,sequence=seq,sector=p[10],binding=entry.binding,
   buffer=entry.buffer,arrival=arrival,source_time=t,position={x,y,z},rate=rate}
  deadline=last+c.timeout;state='pending'
  local ok,v=pcall(entry.binding.begin,entry.binding,{epoch=c.epoch,generation=c.generation,index=index,sequence=seq,sector_macro=p[10]},arrival)
  return ok and v==true and state=='pending' and check()
 end
 function api:tick()
  if busy or (state~='ready' and state~='pending') then return fail('tick')end
  busy=true;local ok=pcall(function()
   assert(check())
   if state=='pending' then assert(pending.binding:tick() and check())end
   local packet=c.net:receive()
   if packet~=nil then assert(state=='ready' and accept(packet))end
  end);busy=false;if not ok then return fail('tick')end;return true
 end
 function api:event(value)
  if busy or state~='pending' or delivered then return fail('event')end
  busy=true;local ok=pcall(function()
   assert(check());local accepted=pending.binding:event(value)
   assert(accepted==true and delivered==true and state=='pending' and check())
   local pose={pending.position[1],pending.position[2],pending.position[3]}
   local rate=pending.rate and {pending.rate[1],pending.rate[2],pending.rate[3]} or nil
   local snapshot={frame=pending.sector,sequence=pending.sequence,source_time=pending.source_time,pose=pose,rate=rate}
   local function vector_unchanged(v,expected)
    if type(v)~='table' or getmetatable(v)~=nil or #v~=3 then return false end
    for k in pairs(v)do if type(k)~='number' or k%1~=0 or k<1 or k>3 then return false end end
    return v[1]==expected[1] and v[2]==expected[2] and v[3]==expected[3]
   end
   local function snapshot_unchanged()
    if getmetatable(snapshot)~=nil or snapshot.frame~=pending.sector or snapshot.sequence~=pending.sequence or
       snapshot.source_time~=pending.source_time or snapshot.pose~=pose or snapshot.rate~=rate or
       not vector_unchanged(pose,pending.position) then return false end
    for k in pairs(snapshot)do if k~='frame' and k~='sequence' and k~='source_time' and k~='pose' and k~='rate' then return false end end
    return not rate or vector_unchanged(rate,pending.rate)
   end
   local pushed=pending.buffer:push(snapshot,pending.arrival)
   assert(pushed==true and state=='pending' and check() and snapshot_unchanged())
   if c.audit then
    local good,accepted=pcall(c.audit,pending.index,pending.sequence,pending.sector,pending.source_time)
    assert(good and accepted==true and state=='pending' and check() and snapshot_unchanged())
   end
   assert(c.net:receive()==nil and check() and snapshot_unchanged())
   assert(send(reply('BOUND',pending.identity)));pending=nil;deadline=nil;delivered=nil;state='ready'
  end);busy=false;if not ok then return fail('event')end;return true
 end
 function api:state()return state end
 return api
end
function M.new_x4(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(type(o.binding)=='table' and type(o.binding.new_x4)=='function' and type(RegisterEvent)=='function' and type(GetCurRealTime)=='function')
 assert(not registered,'motion event router already reserved');registered=true
 local c={};for k,v in pairs(o)do c[k]=v end
 local register=RegisterEvent;local native=c.binding.new_x4;c.clock=GetCurRealTime
 c.register=function(fn)return register('X4AuthorityReplicaMotionBind.Result',fn)~=false end
 c.factory=function(opt)
  opt.enabled=true;opt.expected_save_path=c.expected_save_path;opt.guard=c.guard;opt.resolve=c.resolve
  return native(opt)
 end
 return M.new(c)
end
X4LAN_MOTION_CLIENT_OWNER=M
return M
