-- Local diagnostic owner. Caller exclusively owns callbacks, update and process fencing.
-- No network output, actor creation or registry mutation.
local M={}
local MAX=9007199254740991
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function finite(v)return type(v)=='number' and v==v and v>=0 and v<math.huge end
local function integer(v,min)return finite(v) and v>=min and v<=MAX and v%1==0 end
local function decimal(v,min)
 if type(v)~='string' or #v>16 or not v:match('^%d+$') or (#v>1 and v:sub(1,1)=='0') then return nil end
 local n=tonumber(v);if not integer(n,min) or string.format('%.0f',n)~=v then return nil end;return n
end
local function split(v)local out={};for x in (v..'|'):gmatch('(.-)|')do out[#out+1]=x end;return out end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.generation) and o.epoch~=o.generation and integer(o.capacity,1) and o.capacity<=1024)
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=300)
 local epoch,generation,capacity,timeout=o.epoch,o.generation,o.capacity,o.timeout
 local cb={};for _,k in ipairs({'register','issue','clock','guard','actor_key','report','fault'})do assert(type(o[k])=='function');cb[k]=o[k] end
 local state,busy='new',false;local last,deadline,sequence,request,request_no=nil,nil,1,nil,0
 local api={}
 local function fail(reason)
  if state~='failed' then state='failed';pcall(cb.fault,reason) end
  return false,reason
 end
 local function check()
  local ok,t=pcall(cb.clock);if not ok or not finite(t) or (last and t<last) or (deadline and t>=deadline) then return false end
  last=t;local good,allowed=pcall(cb.guard)
  if not good or allowed~=true or state=='failed' then return false end
  local again,u=pcall(cb.clock);if not again or not finite(u) or u<t or (deadline and u>=deadline) then return false end
  last=u;return true
 end
 local function send(op,args,next)
  if not check() then return fail('guard') end
  state=next;deadline=last+timeout
  if not finite(deadline) then return fail('deadline') end
  local ok,sent=pcall(cb.issue,'X4AuthorityShipEventCompare',op,args)
  if not ok or sent~=true or state~=next or not check() then return fail('dispatch') end
  return true
 end
 local function issue(op,next,extra)
  if request_no>=MAX then return fail('request_capacity') end
  request_no=request_no+1;request=generation..'-'..string.format('%.0f',request_no)
  local args={epoch=epoch,generation=generation,request_id=request}
  if extra then args.sequence=extra end
  return send(op,args,next)
 end
 local function receive(name,value)
  if busy then return fail('reentrant') end
  busy=true
  local ok,result=pcall(function()
   assert(check(),'guard')
   if name=='Faulted' then error('md_fault') end
   if state=='initializing' and name=='Initialized' and value==generation then state='idle';deadline=nil;return true end
   assert(name=='Result' and type(value)=='string' and #value<=256,'unexpected_event')
   local p=split(value);assert(p[1]==request,'request_mismatch')
   if state=='front' and #p==2 and p[2]=='empty' then state='idle';deadline=nil;return true end
   if state=='front' and #p==6 and p[2]=='item' then
    local seq,idx=decimal(p[3],1),decimal(p[5],0)
    assert(seq==sequence and idx and (p[4]=='god' or p[4]=='player_build' or p[4]=='activation' or p[4]=='galaxy_enter'),'invalid_row')
    local k=cb.actor_key(p[6]);assert(type(k)=='string' and #k<=20 and k:match('^[1-9]%d*$'),'actor_key')
    local row={sequence=sequence,kind=p[4],registry_index=idx,actor_key=k}
    assert(cb.report(row)==true and row.sequence==sequence and row.kind==p[4] and row.registry_index==idx and row.actor_key==k,'report')
    assert(state=='front' and check(),'report_guard')
    return issue('Ack','acking',sequence)
   end
   if state=='acking' and #p==3 and p[2]=='acked' and decimal(p[3],1)==sequence then
    assert(sequence<2147483647,'capacity');sequence=sequence+1;state='idle';deadline=nil;return true
   end
   error('unexpected_event')
  end)
  busy=false
  if not ok or result~=true then return fail(ok and 'response' or tostring(result)) end
  return true
 end
 function api:start()
  if busy or state~='new' then return fail('start') end
  busy=true
  for _,name in ipairs({'Initialized','Result','Faulted'})do
   local event=name;local ok,accepted=pcall(cb.register,'X4AuthorityShipEventCompare.'..event,function(_,v)receive(event,v)end)
   if not ok or accepted~=true or state~='new' then busy=false;return fail('register') end
  end
  local ok=send('Initialize',{epoch=epoch,generation=generation,capacity=capacity},'initializing');busy=false;return ok
 end
 function api:tick()
  if busy or state=='failed' or state=='new' then return fail('tick') end
  busy=true;local ok
  if state=='idle' then ok=issue('Front','front') else ok=check() end
  busy=false;if not ok then return fail('tick_guard') end;return true
 end
 function api:state()return state end
 return api
end
-- The MD hexadecimal text must exactly round-trip through native conversions.
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(type(c.resolve)=='table' and type(c.resolve.actor_u64)=='function' and type(c.resolve.parse_hex)=='function' and type(c.guard)=='function')
 assert(type(RegisterEvent)=='function' and type(AddUITriggeredEvent)=='function' and type(GetCurRealTime)=='function' and type(ConvertIDTo64Bit)=='function' and type(ConvertStringToLuaID)=='function')
 local resolve,parse,convert,to_lua=c.resolve.actor_u64,c.resolve.parse_hex,ConvertIDTo64Bit,ConvertStringToLuaID
 local ffi=require('ffi');if not pcall(ffi.typeof,'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 ffi.cdef[[bool IsValidComponent(UniverseID); bool IsComponentClass(UniverseID,const char*);]]
 local C=ffi.C
 local options={};for k,v in pairs(c)do options[k]=v end
 options.register=function(n,f)return RegisterEvent(n,f)~=false end
 options.issue=function(s,op,args)return AddUITriggeredEvent(s,op,args)~=false end
 options.clock=GetCurRealTime
 options.actor_key=function(text)
  local id=parse(text);assert(id)
  local key=tostring(id):gsub('ULL$','');assert(key:match('^[1-9]%d*$'))
  local ref=to_lua(key);assert(ref~=nil and ref~=false)
  local kind=type(ref)
  if kind=='number' then assert(integer(ref,1))
  else assert(kind=='cdata' or kind=='userdata') end
  local converted=resolve(convert(ref));assert(converted and id==converted and C.IsValidComponent(id) and C.IsComponentClass(id,'ship'))
  return key
 end
 return M.new(options)
end
return M
