-- Opt-in, serial source-job client owner. Caller owns the update hook and UDP.
local M={}
local MAX=9007199254740991
local function token(v,n)return type(v)=='string' and #v==n and v:match('^[0-9a-f]+$')~=nil end
local function integer(v,min)return type(v)=='number' and v==v and v>=min and v<=MAX and v%1==0 end
local function number(v)
 if type(v)~='string' or #v==0 or #v>32 or not v:match('^[%d%.%+%-eE]+$') then return nil end
 local n=tonumber(v);if not n or n~=n or math.abs(n)>10000000 then return nil end;return n
end
local function natural(v)
 if type(v)~='string' or not v:match('^[1-9]%d*$') or #v>16 then return nil end
 local n=tonumber(v);if not integer(n,1) or string.format('%.0f',n)~=v then return nil end;return n
end
local function reason(v)
 if type(v)=='string' and #v<=40 and v:match('^[a-z0-9_]+$') then return v end
 return 'unknown'
end
local function name(v)return type(v)=='string' and #v>=1 and #v<=128 and v:match('^[A-Za-z0-9_]+$')~=nil end
local function split(v)local p={};for s in (v..'|'):gmatch('(.-)|')do p[#p+1]=s end;return p end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local frozen={};for k,v in pairs(o)do frozen[k]=v end;o=frozen
 for _,v in ipairs({o.lease,o.attempt,o.epoch,o.generation,o.nonce})do assert(token(v,32))end
 assert(o.lease~=o.attempt and o.lease~=o.epoch and o.lease~=o.generation and o.attempt~=o.epoch and o.attempt~=o.generation and o.epoch~=o.generation)
 assert(integer(o.baseline,1) and integer(o.seed,0) and o.seed<=2147483647)
 assert(type(o.timeout)=='number' and o.timeout>0 and o.timeout<=30)
 assert(o.audit==nil or type(o.audit)=='function')
 assert(o.witness_audit==nil or type(o.witness_audit)=='function')
 for _,k in ipairs({'clock','guard','issue','witness','fault'})do assert(type(o[k])=='function',k..' required')end
 assert(type(o.client)=='table' and type(o.client.new)=='function' and type(o.inspector)=='table' and type(o.inspector.inspect)=='function' and type(o.inspector.arm_running)=='function')
 assert((type(o.net)=='table' or type(o.net)=='userdata') and type(o.net.send)=='function' and type(o.net.receive)=='function')
 local phase,busy,failed='new',false,false
 local last,deadline,pending,delivered,last_seq=nil,nil,nil,nil,0
 local client
 local function fail(reason)
  if not failed then failed=true;phase='failed';pcall(o.fault,reason)end
  return false
 end
 local function call(fn,...)
  local old=phase;local ok,a,b=pcall(fn,...)
  if not ok or failed or phase~=old then return false end
  return true,a,b
 end
 local function check()
  if failed then return false end
  local ok,t=call(o.clock)
  if not ok or type(t)~='number' or t~=t or t<0 or t==math.huge or (last and t<last) or (deadline and t>=deadline) then return false end
  last=t;local valid,g=call(o.guard)
  if not valid or g~=true then return false end
  local ok2,t2=call(o.clock)
  if not ok2 or type(t2)~='number' or t2~=t2 or t2<t or t2==math.huge or (deadline and t2>=deadline) then return false end
  last=t2;return true
 end
 local function send(raw)
  if #raw>768 or not check() then return false end
  local ok,result=call(o.net.send,o.net,raw)
  return ok and result==true and check()
 end
 local function response(kind)
  local p={'X',o.lease,o.attempt,kind}
  if kind=='READY' then p[#p+1]=o.epoch;p[#p+1]=o.generation
  else for _,v in ipairs(pending.identity)do p[#p+1]=v end end
  return table.concat(p,'|')
 end
 client=assert(o.client.new({enabled=true,epoch=o.epoch,nonce=o.nonce,baseline=o.baseline,timeout=o.timeout,
  clock=o.clock,guard=o.guard,issue=o.issue,witness_audit=o.witness_audit,
  inspect=function(...)return o.inspector:inspect(...)end,
  complete=function(kind,result)
   if delivered or (phase=='initializing' and (kind~='initialize' or result.epoch~=o.epoch)) or
      (phase=='applying' and (kind~='create' or not pending or result.index~=pending.index)) or
      (phase~='initializing' and phase~='applying') then return false end
   delivered=kind;return true
  end}))
 local api={}
 function api:start()
  if busy or phase~='new' then return fail('start') end
  busy=true
  if not check() then busy=false;return fail('guard') end
  phase='initializing';deadline=last+o.timeout
  local ok,result=pcall(client.initialize,client);busy=false
  if not ok or result~=true or failed or phase~='initializing' then return fail('initialize') end
  return true
 end
 function api:event(value)
  if busy or failed or delivered or (phase~='initializing' and phase~='applying') then return fail('unexpected_event') end
  busy=true
  if not check() then busy=false;return fail('guard') end
  local ok,result,detail=pcall(client.event,client,value)
  if not ok or result~=true or failed or not check() then busy=false;return fail('event_'..reason(detail)) end
  if delivered then
   if phase=='initializing' and delivered=='initialize' then phase='announce'
   elseif phase=='applying' and delivered=='create' then phase='reply'
   else busy=false;return fail('completion') end
   delivered=nil
  end
  busy=false;return true
 end
 local function accept(raw)
  if type(raw)~='string' or #raw>768 or phase~='ready' then return false end
  local p=split(raw)
  if #p~=16 or p[1]~='P' or p[2]~=o.lease or p[3]~=o.attempt or p[4]~='APPLY' or
     not token(p[5],32) or p[6]~=o.epoch or p[7]~=o.generation or not token(p[10],64) then return false end
  local sequence,index=natural(p[8]),natural(p[9]);local x,y,z=number(p[14]),number(p[15]),number(p[16])
  if not sequence or sequence~=last_seq+1 or not index or not name(p[11]) or not name(p[12]) or not name(p[13]) or not x or not y or not z then return false end
  local ok,w=call(o.witness,p[13]);if not ok or not check() then return false,'witness' end
  local candidates
  if type(w)=='table' then
   if getmetatable(w)~=nil then return false,'witness' end
   local count=0
   for k in pairs(w)do if not integer(k,1) or k>o.baseline then return false,'witness' end;count=count+1 end
   if count==0 or count>o.baseline then return false,'witness' end
   candidates={};local previous=0
   for i=1,count do
    local v=rawget(w,i)
    if not integer(v,1) or v>o.baseline or v<=previous then return false,'witness' end
    candidates[i]=v;previous=v
   end
   w=candidates[1]
  elseif not integer(w,1) or w>o.baseline then return false,'witness' end
  pending={index=index,identity={p[5],p[6],p[7],p[8],p[9],p[10]}}
  deadline=last+o.timeout;phase='applying'
  local armed,value=call(o.inspector.arm_running,o.inspector)
  if not armed or value~=true or not check() then return false,'inspector_arm' end
  local sent,accepted,detail=call(client.create,client,{index=index,macro=p[11],owner=p[12],sector=p[13],seed=o.seed,x=x,y=y,z=z,witness_index=w},candidates)
  if not sent or accepted~=true then return false,'create_'..reason(detail) end
  if not check() then return false,'create_guard' end
  return true
 end
 function api:tick()
  if busy or failed or phase=='new' then return fail('tick_state') end
  busy=true
  if not check() then busy=false;return fail('guard') end
  local ok,result,detail=call(client.tick,client)
  if not ok or result~=true or not check() then busy=false;return fail('client_tick_'..reason(detail)) end
  if phase=='announce' then
   if not send(response('READY')) then busy=false;return fail('ready_send') end
   deadline=nil;phase='ready'
  elseif phase=='reply' then
   if o.audit then
    local noted,accepted=call(o.audit,pending.index)
    if not noted or accepted~=true or not check() then busy=false;return fail('audit') end
   end
   if not pending or not send(response('APPLIED')) then busy=false;return fail('applied_send') end
   last_seq=last_seq+1;pending=nil;deadline=nil;phase='ready'
  end
  local got,packet=call(o.net.receive,o.net)
  if not got then busy=false;return fail('receive') end
  if packet~=nil then
   local accepted,detail=accept(packet)
   if not accepted then busy=false;return fail('packet_'..reason(detail)) end
  end
  busy=false;return true
 end
 function api:state()return phase end
 return api
end
-- This factory installs exactly one event router, never an onUpdate hook.
-- Call start/tick from the same exclusive onUpdate as participant control.
local registered=false
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(not registered,'event router already reserved')
 assert(type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save')
 assert(type(c.guard)=='function' and type(c.witness)=='function' and type(c.fault)=='function')
 assert(type(c.inspector_module)=='table' and type(c.inspector_module.new_x4)=='function')
 for _,k in ipairs({'RegisterEvent','AddUITriggeredEvent','GetCurRealTime'})do assert(type(_G[k])=='function')end
 local expected,external=c.expected_save_path,c.guard
 local ffi=require('ffi');ffi.cdef[[const char* GetSaveFolderPath(void);bool IsPlayerValid(void);bool IsGamePaused(void);double GetCurrentGameTime(void);]]
 local C=ffi.C;local last_game
 local function environment()
  local path=C.GetSaveFolderPath()
  return path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==expected and C.IsPlayerValid() and not C.IsGamePaused()
 end
 local function guard()
  if not environment() or external()~=true or not environment() then return false end
  local g=tonumber(C.GetCurrentGameTime())
  if not g or g~=g or g<0 or g==math.huge or (last_game and g<last_game) or not environment() then return false end
  last_game=g;return true
 end
 local inspector=assert(c.inspector_module.new_x4({enabled=true,running=true,md_inspected=true,frame_confirmed=true,
  expected_save_path=expected,guard=guard,timeout=c.timeout,position_tolerance=c.position_tolerance,resolve=c.resolve}))
 local options={};for k,v in pairs(c)do options[k]=v end
 options.inspector=inspector;options.guard=guard;options.clock=GetCurRealTime
 options.issue=function(screen,operation,args)return AddUITriggeredEvent(screen,operation,args)~=false end
 local owner=assert(M.new(options));registered=true
 assert(RegisterEvent('X4AuthorityMultiCreateReceiver.Result',function(_,value)owner:event(value)end)~=false)
 return owner
end
X4LAN_AUTHORITY_JOB_CLIENT_OWNER=M
return M
