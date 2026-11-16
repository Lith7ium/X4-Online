-- Opt-in one-owner UDP glue. No hooks, X4 calls or sockets on import.
-- net is an already connected nonblocking x4lan_net UDP object. The outer
-- update owner must call tick only; callbacks below merely record intentions.
local M={}
local function token(s)return type(s)=='string' and #s==32 and s:match('^[0-9a-f]+$')~=nil end
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function name(s)return type(s)=='string' and #s>0 and #s<=128 and s:match('^[%w_%-%.]+$')~=nil end
local function split(s)
 local out={};for value in (s..'|'):gmatch('(.-)|') do out[#out+1]=value end;return out
end
local function number(s)
 if type(s)~='string' or #s==0 or #s>32 or not s:match('^[%d%.%+%-eE]+$') then return nil end
 local n=tonumber(s);if not finite(n) or math.abs(n)>10000000 then return nil end;return n
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert((o.role=='server' or o.role=='client') and token(o.lease) and token(o.attempt) and token(o.epoch) and name(o.sector))
 assert(type(o.net)=='table' or type(o.net)=='userdata')
 assert(type(o.net.send)=='function' and type(o.net.receive)=='function' and type(o.net.close)=='function')
 for _,k in ipairs({'clock','pair_guard','owner_factory','log'}) do assert(type(o[k])=='function',k..' required') end
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=600)
 local phase='new';local failed,busy=false,false;local owner;local last,deadline;local intent
 local check_counter,pending_check=0,nil
 local prefix=table.concat({'PAIR',o.lease,o.role,o.attempt,o.epoch},'|')
 local command=table.concat({'CMD',o.lease,o.role,o.attempt,o.epoch},'|')
 local function log(label)return pcall(o.log,label)end
 local function fail()
  if not failed then
   failed=true;phase='failed';log('FAULT')
   pcall(function()o.net:send(prefix..'|FAULT')end)
  end
  return false
 end
 local function check()
  if failed then return false end
  local ok,t=pcall(o.clock)
  if not ok or not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return fail() end
  last=t
  local good,ready=pcall(o.pair_guard)
  if not good or ready~=true or failed then return fail() end
  local done,after=pcall(o.clock)
  if not done or not finite(after) or after<t or (deadline and after>=deadline) then return fail() end
  last=after;return true
 end
 local function emit(label,rest)
  if not check() then return false end
  local text=prefix..'|'..label..(rest and ('|'..rest) or '')
  if #text>768 then return fail() end
  local ok,sent=pcall(o.net.send,o.net,text)
  if not ok or sent~=true or not check() then return fail() end
  if not log(label) then return fail() end;return true
 end
 local function fault()fail() end
 local function descriptor_intent(v)
  if failed or o.role~='server' or intent~=nil or type(v)~='table' then return fail() end
  local copy={};local allowed={attempt=true,epoch=true,sequence=true,index=true,macro=true,sector=true,owner=true,seed=true,x=true,y=true,z=true}
  local n=0;for k,x in pairs(v) do if not allowed[k] then return fail() end;copy[k]=x;n=n+1 end
  if n~=11 or copy.attempt~=o.attempt or copy.epoch~=o.epoch or copy.sequence~=1 or copy.index~=3 or copy.macro~='ship_arg_s_fighter_01_a_macro' or copy.sector~=o.sector or copy.owner~='argon' or copy.seed~=7183 then return fail() end
  for _,k in ipairs({'x','y','z'}) do if not finite(copy[k]) or math.abs(copy[k])>10000000 then return fail() end end
  intent=copy;return true
 end
 local function completion_intent(v)
  if failed or o.role~='client' or intent~=nil or type(v)~='table' then return fail() end
  local allowed={attempt=true,epoch=true,sequence=true,index=true};local n=0
  for k in pairs(v) do if not allowed[k] then return fail() end;n=n+1 end
  if n~=4 or v.attempt~=o.attempt or v.epoch~=o.epoch or v.sequence~=1 or v.index~=3 then return fail() end
  intent=true;return true
 end
 local function received(packet)
  if type(packet)~='string' or #packet>768 then return fail() end
  local p=split(packet)
  if #p<6 or table.concat({p[1],p[2],p[3],p[4],p[5]},'|')~=command then return fail() end
  if p[6]=='CHECK' and #p==7 then
   if pending_check or not p[7]:match('^[1-9]%d*$') or #p[7]>10 then return fail() end
   local n=tonumber(p[7]);if not n or n>2147483647 or n<=check_counter then return fail() end
   check_counter=n;pending_check=n;return true
  elseif p[6]=='START' and #p==6 and phase=='ready' then
   phase='running';local ok,started=pcall(owner.start,owner)
   if not ok or started~=true or failed then return fail() end
   return true
  elseif p[6]=='DESCRIPTOR' and #p==15 and phase=='await_descriptor' and o.role=='client' and p[7]=='1' and p[8]=='3' then
   local v={attempt=o.attempt,epoch=o.epoch,sequence=1,index=3,macro=p[9],sector=p[10],owner=p[11],seed=tonumber(p[12]),x=number(p[13]),y=number(p[14]),z=number(p[15])}
   if p[12]~='7183' or v.x==nil or v.y==nil or v.z==nil then return fail() end
   phase='running';local ok,accepted=pcall(owner.accept_descriptor,owner,v)
   if not ok or accepted~=true or failed then return fail() end
   return true
  elseif p[6]=='ACK' and #p==8 and phase=='await_ack' and o.role=='server' and p[7]=='1' and p[8]=='3' then
   phase='running';local ok,accepted=pcall(owner.confirm_ack,owner,{attempt=o.attempt,epoch=o.epoch,sequence=1,index=3})
   if not ok or accepted~=true or failed then return fail() end
   return true
  end
  return fail()
 end
 local api={}
 function api:tick()
  if failed then return false end
  if busy then return fail() end
  busy=true
  local ok=pcall(function()
   if phase=='new' then
    local valid,t=pcall(o.clock);assert(valid and finite(t) and t>=0);last=t;deadline=t+o.timeout
    assert(finite(deadline) and check())
    owner=assert(o.owner_factory(descriptor_intent,completion_intent,fault));assert(not failed)
    phase='ready';assert(emit('READY'))
   end
   assert(check())
   for _=1,4 do
    local packet=o.net:receive();if packet==nil then break end
    assert(received(packet))
   end
   if phase~='ready' then
    assert(check());local valid,alive,current=pcall(owner.update,owner)
    assert(valid and alive==true and not failed and check())
    if phase=='running' and o.role=='client' and current=='await_descriptor' then
     phase='await_descriptor';assert(emit('AWAIT'))
    elseif phase=='running' and o.role=='server' and current=='await_ack' then
     assert(type(intent)=='table')
     local v=intent;intent=nil;phase='await_ack'
     local tail=table.concat({'1','3',v.macro,v.sector,v.owner,tostring(v.seed),string.format('%.17g',v.x),string.format('%.17g',v.y),string.format('%.17g',v.z)},'|')
     assert(emit('DESCRIPTOR',tail))
    elseif phase=='running' and o.role=='client' and current=='done' then
     assert(intent==true);intent=nil;phase='finished';assert(emit('INSPECTED','1|3'))
    elseif phase=='running' and o.role=='server' and current=='done' then
     phase='finished';assert(emit('FINISHED','1|3'))
    end
   end
   if pending_check then local n=pending_check;pending_check=nil;assert(emit('CHECKED',tostring(n))) end
  end)
  busy=false
  if not ok or failed then return fail() end
  return true,phase
 end
 function api:state()return phase end
 function api:close() local ok=pcall(o.net.close,o.net);if not ok then return fail() end;return true end
 return api
end

-- Call explicitly, only after the local pair-ready check. The existing single
-- update owner must keep calling tick; this function installs no script hook.
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(type(c.pair_guard)=='function' and c.pair_guard()==true and type(c.driver)=='table' and type(c.adapter)=='table')
 assert(type(c.port)=='number' and c.port%1==0 and c.port>=1 and c.port<=65535)
 assert(type(GetCurRealTime)=='function' and type(DebugError)=='function')
 local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
 local net=assert(lib.open('127.0.0.1',c.port))
 local ok,result=pcall(function()
  return assert(M.new({enabled=true,role=c.role,lease=c.lease,attempt=c.attempt,epoch=c.epoch,sector=c.sector,timeout=c.timeout,
   net=net,clock=GetCurRealTime,pair_guard=c.pair_guard,
   log=function(s)DebugError('[X4LAN] AUTH_PAIR_CREATE '..(s=='FAULT' and 'ERROR FAULT' or s))end,
   owner_factory=function(desc,complete,fault)
    return assert(c.adapter.new({enabled=true,exclusive_events=true,driver=c.driver,
     role=c.role=='server' and 'source' or 'client',epoch=c.epoch,attempt=c.attempt,nonce=c.nonce,
     sector=c.sector,timeout=math.min(c.timeout,120),expected_save_path=c.expected_save_path,
     emit_descriptor=desc,inspect_complete=complete,fault=fault}))
   end}))
 end)
 if not ok then pcall(net.close,net);error('pair UDP setup failed') end
 return result
end
return M
