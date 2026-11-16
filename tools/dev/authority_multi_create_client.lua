-- Default-off experimental serial client; no X4 calls or registrations.
local M={}
local SCREEN='X4AuthorityMultiCreateReceiver'
local MAX=9007199254740991
local fields={'macro','sector','owner','seed','x','y','z'}
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function integer(v,min)return type(v)=='number' and v==v and v>=min and v<=MAX and v%1==0 end
local function finite(v)return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge end
local function name(v)return type(v)=='string' and #v>0 and #v<=128 and v:match('^[%w_%-%.]+$')~=nil end
local function actor_decimal(hex)
 if type(hex)~='string' or #hex>18 or not hex:match('^0[xX][0-9a-fA-F]+$') then return nil end
 local s='0'
 for i=3,#hex do
  local carry=tonumber(hex:sub(i,i),16);local out={}
  for j=#s,1,-1 do local n=(s:byte(j)-48)*16+carry;out[#out+1]=string.char(48+n%10);carry=math.floor(n/10) end
  while carry>0 do out[#out+1]=string.char(48+carry%10);carry=math.floor(carry/10) end
  s=table.concat(out):reverse():gsub('^0+','');if s=='' then s='0' end
 end
 return s~='0' and s or nil
end
local function descriptor(d,baseline)
 if type(d)~='table' or getmetatable(d)~=nil then return nil end
 local allowed={index=true,macro=true,sector=true,owner=true,seed=true,x=true,y=true,z=true,witness_index=true}
 for k in pairs(d)do if not allowed[k] then return nil end end
 if not integer(d.index,1) or not name(d.macro) or not name(d.sector) or not integer(d.witness_index,1) or d.witness_index>baseline or
  not name(d.owner) or not integer(d.seed,0) or d.seed>2147483647 then return nil end
 for _,k in ipairs({'x','y','z'})do if not finite(d[k]) or math.abs(d[k])>10000000 then return nil end end
 local copy={index=d.index,witness_index=d.witness_index};for _,k in ipairs(fields)do copy[k]=d[k] end;return copy
end
local function same(a,b)
 if not a or not b or a.index~=b.index then return false end
 for _,k in ipairs(fields)do if a[k]~=b[k] then return false end end
 return true
end
local function same_result(a,b)
 if type(a)~='table' or getmetatable(a)~=nil then return false end
 for k,v in pairs(a)do if b[k]~=v then return false end end
 for k,v in pairs(b)do if a[k]~=v then return false end end
 return true
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.nonce) and integer(o.baseline,1))
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=300)
 for _,k in ipairs({'clock','guard','issue','inspect','complete'})do assert(type(o[k])=='function',k..' required')end
 local phase,busy,issuing='new',false,false
 local last,deadline,request_seq,pending,highest=nil,nil,0,nil,o.baseline
 local records,actors={},{}
 local api={}
 local function fail(reason)phase='failed';pending=nil;deadline=nil;return false,reason end
 local function call(fn,...)
  if busy then return fail('reentrant') end
  local old=phase;busy=true;local ok,a,b=pcall(fn,...);busy=false
  if not ok or phase~=old then return fail('callback') end
  return true,a,b
 end
 local function check()
  if phase=='failed' or phase=='closed' then return false end
  local ok,t=call(o.clock)
  if not ok or not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) then return fail('clock_or_timeout') end
  last=t
  local valid,guard=call(o.guard);if not valid or guard~=true then return fail('guard') end
  local checked,after=call(o.clock)
  if not checked or not finite(after) or after<t or (deadline and after>=deadline) then return fail('clock_or_timeout') end
  last=after;return true
 end
 local function dispatch(op,args,kind,d,actor)
  if not check() then return false end
  if request_seq>=MAX then return fail('request_capacity') end
  request_seq=request_seq+1;local id=o.nonce..'-'..string.format('%.0f',request_seq)
  pending={id=id,kind=kind,descriptor=d,actor=actor};deadline=last+o.timeout
  if not finite(deadline) then return fail('deadline') end
  args.request_id=id;phase='pending';issuing=true
  local ok,sent=call(o.issue,SCREEN,op,args);issuing=false
  if not ok or sent~=true then return fail('dispatch') end
  return check()
 end
 function api:initialize()
  if phase~='new' then return fail('initialize_state') end
  return dispatch('Initialize',{epoch=o.epoch,baseline=o.baseline},'initialize')
 end
 function api:create(value)
  if phase~='ready' then return fail('create_state') end
  local d=descriptor(value,o.baseline);if not d then return fail('descriptor') end
  local old=records[d.index];local kind
  if old then if not same(old.descriptor,d) then return fail('descriptor_conflict') end;kind='replay'
  else if highest>=MAX or d.index~=highest+1 then return fail('index_gap_or_unknown') end;kind='create' end
  local args={epoch=o.epoch};for k,v in pairs(d)do args[k]=v end
  return dispatch('Create',args,kind,d)
 end
 function api:event(value)
  if phase~='pending' or issuing then return fail('unexpected_event') end
  if not check() or type(value)~='string' or #value>512 then return fail('invalid_event') end
  local id,kind,rest=value:match('^([0-9a-f]+%-%d+)|([A-Za-z]+)|(.*)$')
  if id~=pending.id then return fail('correlation') end
  if kind=='Refused' then return fail('refused') end
  if pending.kind=='initialize' then
   if kind~='Initialized' or rest~=o.epoch then return fail('initialize_response') end
   local result={epoch=o.epoch};phase='delivering';local ok,done=call(o.complete,'initialize',result)
   if not ok or done~=true or not same_result(result,{epoch=o.epoch}) or not check() then return fail('completion') end
   pending=nil;deadline=nil;phase='ready';return true
  end
  if pending.kind=='create' or pending.kind=='replay' then
   local index,hex=rest:match('^([1-9]%d*)|(0[xX][0-9a-fA-F]+)$')
   if kind~='Created' or not index or #index>16 or tonumber(index)~=pending.descriptor.index or
     string.format('%.0f',pending.descriptor.index)~=index then return fail('create_response') end
   local expected=actor_decimal(hex);if not expected then return fail('actor_format') end
   local d,operation=pending.descriptor,pending.kind
   local args={epoch=o.epoch};for k,v in pairs(d)do args[k]=v end
   return dispatch('Inspect',args,'inspect_'..operation,d,expected)
  end
  if pending.kind~='inspect_create' and pending.kind~='inspect_replay' then return fail('unexpected_operation') end
  local index,hex,sector=rest:match('^([1-9]%d*)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)$')
  if kind~='Inspected' or not index or #index>16 or tonumber(index)~=pending.descriptor.index or
    string.format('%.0f',pending.descriptor.index)~=index then return fail('inspect_response') end
  local expected=actor_decimal(hex);if not expected or expected~=pending.actor or not actor_decimal(sector) then return fail('actor_format') end
  local view=descriptor(pending.descriptor,o.baseline)
  local ok,actor_key,binding=call(o.inspect,hex,sector,pending.descriptor.index,view)
  if not ok or not descriptor(view,o.baseline) or not same(view,pending.descriptor) or view.witness_index~=pending.descriptor.witness_index or
    actor_key~=expected or binding~=true or not check() then return fail('actor_binding') end
  local d,operation=pending.descriptor,pending.kind=='inspect_create' and 'create' or 'replay';local old=records[d.index]
  if operation=='replay' then
   if not old or old.actor~=actor_key or not same(old.descriptor,d) then return fail('replay_binding') end
  elseif old or actors[actor_key] or d.index~=highest+1 then return fail('actor_collision') end
  local result={index=d.index,actor_key=actor_key};phase='delivering';local delivered,accepted=call(o.complete,operation,result)
  if not delivered or accepted~=true or not same_result(result,{index=d.index,actor_key=actor_key}) or not check() then return fail('completion') end
  if operation=='create' then records[d.index]={descriptor=d,actor=actor_key};actors[actor_key]=d.index;highest=d.index end
  pending=nil;deadline=nil;phase='ready';return true
 end
 function api:tick()return check()end
 function api:state()return phase end
 function api:close()phase='closed';pending=nil;deadline=nil;return true end
 return api
end
return M
