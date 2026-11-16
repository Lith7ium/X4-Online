-- Default-off client-only wrapper. One connected UDP socket and the existing
-- Census owner remain the sole onUpdate owner; no X4 hooks on import.
local M={}
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function natural(v)return finite(v) and v>=1 and v<=9007199254740991 and v%1==0 end
local function name(v)return type(v)=='string' and #v>0 and #v<=128 and v:match('^[%w_%-%.]+$')~=nil and v:lower()~='nil' and v:lower()~='null' end
local function split(v)local r={};for x in (v..'|'):gmatch('(.-)|')do r[#r+1]=x end;return r end
local function number(s)
 if type(s)~='string' or #s==0 or #s>32 or not s:match('^[%d%.%+%-eE]+$') then return nil end
 local n=tonumber(s);if not finite(n) or math.abs(n)>10000000 then return nil end;return n
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.lease) and token(o.attempt) and token(o.epoch) and (type(o.net)=='userdata' or type(o.net)=='table'))
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=600)
 for _,k in ipairs({'clock','guard','log','replica_log','base_factory','replica_factory'})do assert(type(o[k])=='function',k..' required')end
 local phase='running';local failed,busy=false,false;local base,replica,witness,descriptor,intent,last,deadline
 local inbound={};local prefix=table.concat({'CENSUS',o.lease,'client',o.attempt,o.epoch},'|')
 local command=table.concat({'CMD',o.lease,'client',o.attempt,o.epoch},'|')
 local function fail()
  if not failed then failed=true;phase='failed';pcall(o.replica_log,'FAULT');if base then pcall(base.fault,base) else pcall(o.net.send,o.net,prefix..'|FAULT') end end
  return false
 end
 local function check()
  if failed then return false end
  local ok,t=pcall(o.clock);if not ok or not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return fail() end;last=t
  local good,v=pcall(o.guard);if not good or v~=true or failed then return fail() end
  local yes,after=pcall(o.clock);if not yes or not finite(after) or after<t or (deadline and after>=deadline) then return fail() end;last=after
  return true
 end
 local proxy={}
 function proxy:receive()return table.remove(inbound,1)end
 function proxy:close()return true end -- wrapper owns the real socket
 function proxy:send(packet)
  if type(packet)~='string' or #packet>768 then return fail() end
  local p=split(packet)
  if p[1]=='CENSUS' and p[2]==o.lease and p[3]=='client' and p[4]==o.attempt and p[5]==o.epoch and p[6]=='WITNESS_OK' then
   if phase~='running' or #p~=9 or not p[7]:match('^[1-9]%d*$') or #p[7]>16 or not p[8]:match('^[1-9]%d*$') or #p[8]>5 then return fail() end
   local seq,index=tonumber(p[7]),tonumber(p[8]);if not natural(seq) or not natural(index) or index>10054 or not name(p[9]) then return fail() end
   witness={epoch=o.epoch,index=index,sector_macro=p[9],local_witness_match=true};intent={job_sequence=seq,index=index,sector_macro=p[9]}
   phase='await_replica';packet=prefix..'|WITNESS_READY|'..p[7]..'|'..p[8]..'|'..p[9]
  elseif p[1]=='CENSUS' and p[2]==o.lease and p[3]=='client' and p[4]==o.attempt and p[5]==o.epoch and p[6]=='FAULT' then
   failed=true;phase='failed';pcall(o.replica_log,'FAULT')
  end
  local ok,sent=pcall(o.net.send,o.net,packet);return ok and sent==true
 end
 local function base_log(label)
  if label=='WITNESS_OK' then label='WITNESS_READY' end
  return o.log(label)
 end
 local ok,b=pcall(o.base_factory,proxy,base_log);if not ok or not b then return nil,'base_setup' end;base=b
 local function request(packet)
  local p=split(packet)
  if #p~=14 or table.concat({p[1],p[2],p[3],p[4],p[5]},'|')~=command or p[6]~='REPLICA' or phase~='await_replica' or not witness or not intent then return fail() end
  if not p[7]:match('^[1-9]%d*$') or #p[7]>16 or p[8]~='10055' then return fail() end
  local seq,x,y,z=tonumber(p[7]),number(p[12]),number(p[13]),number(p[14])
  if not natural(seq) or seq~=intent.job_sequence or not name(p[9]) or not name(p[10]) or p[11]~=intent.sector_macro or x==nil or y==nil or z==nil then return fail() end
  descriptor={version=1,type='job_descriptor',attempt=o.attempt,epoch=o.epoch,transport_sequence=1,job_sequence=seq,index=10055,
   macro=p[9],faction=p[10],sector_macro=p[11],x=x,y=y,z=z}
  if not check() then return false end
  local good,r=pcall(o.replica_factory);if not good or not r then return fail() end;replica=r;phase='replica'
  local started,accepted=pcall(replica.start,replica,descriptor,witness)
  if not started or accepted~=true or not check() then return fail() end
  return true
 end
 local api={}
 function api:tick()
  if failed then return false end;if busy then return fail() end;busy=true
  local ok=pcall(function()
   if not deadline then local t=o.clock();assert(finite(t) and t>=0);last=t;deadline=t+o.timeout;assert(finite(deadline)) end
   assert(check())
   local packet=o.net:receive()
   local deferred
   if packet~=nil then
    assert(type(packet)=='string' and #packet<=768)
    local fields=split(packet)
    if fields[6]=='REPLICA' then deferred=packet else inbound[#inbound+1]=packet end
   end
   local active=base:tick();assert(active==true and not failed and check())
   if deferred then assert(request(deferred)) end
   if phase=='replica' then
    local alive,stage=replica:tick();assert(alive==true and not failed and check())
    if stage=='intent_ready' then
     local ready,data=replica:take_intent()
     assert(ready==true and type(data)=='table' and data.attempt==o.attempt and data.epoch==o.epoch and data.transport_sequence==1 and data.job_sequence==intent.job_sequence and data.index==10055 and check())
     phase='intent_pending'
    end
   elseif phase=='intent_pending' then
    local alive=replica:tick();assert(alive==true and check())
    assert(pcall(o.replica_log,'DONE'))
    local packet_out=prefix..'|WITNESS_OK|'..string.format('%.0f',intent.job_sequence)..'|'..string.format('%.0f',intent.index)..'|'..intent.sector_macro
    assert(o.net:send(packet_out)==true and check());assert(pcall(o.log,'WITNESS_OK'));phase='finished'
   elseif phase=='finished' then
    local alive=replica:tick();assert(alive==true and check())
   end
  end)
  busy=false;if not ok or failed then return fail() end;return true,phase
 end
 local function relay(method,v)
  if busy or failed then return fail() end
  local good,accepted=pcall(method,base,v);if not good or accepted~=true or failed then return fail() end
  return true
 end
 function api:baseline_event(v)return relay(base.baseline_event,v)end
 function api:witness_event(v)return relay(base.witness_event,v)end
 function api:descriptor_event(v)return relay(base.descriptor_event,v)end
 function api:fault()return fail()end
 function api:state()return phase end
 function api:close()local ok=pcall(o.net.close,o.net);if not ok then return fail() end;return true end
 return api
end

-- Pass the original Census owner through a factory so the connected socket is
-- wrapped without opening a second socket or registering a second update owner.
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(c.role=='client' and type(c.base_adapter)=='table' and type(c.base_owner)=='table' and type(c.replica_adapter)=='table' and type(c.replica_driver)=='table')
 local wrapper
 local shim={new=function(opts)
  local log=opts.log
  local wrapped,err=M.new({enabled=true,lease=c.lease,attempt=c.attempt,epoch=c.epoch,timeout=c.timeout,
   net=opts.net,clock=opts.clock,guard=opts.guard,log=log,
   replica_log=function(s)DebugError('[X4LAN] AUTH_CENSUS_REPLICA '..(s=='FAULT' and 'ERROR FAULT' or s))end,
   base_factory=function(proxy,logger)opts.net=proxy;opts.log=logger;return c.base_owner.new(opts)end,
   replica_factory=function()
    return c.replica_adapter.new({enabled=true,exclusive_events=true,driver=c.replica_driver,epoch=c.epoch,attempt=c.attempt,nonce=c.nonce,
     timeout=math.min(c.timeout,120),expected_save_path=c.expected_save_path,guard=opts.guard,release_guard=opts.guard,
     fault=function()if wrapper then wrapper:fault() end end})
   end})
  assert(wrapped,err);wrapper=wrapped;return wrapped
 end}
 local config={};for k,v in pairs(c)do config[k]=v end;config.owner=shim
 return c.base_adapter.new(config)
end
return M
