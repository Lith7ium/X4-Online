-- Read-only registry status owner. The surrounding recovery update owns tick.
local M={}
function M.new(c)
 assert(type(c)=='table' and type(c.nonce)=='string' and #c.nonce==32 and c.nonce:match('^[0-9a-f]+$') and type(c.expected)=='string')
 for _,k in ipairs({'clock','paused','issue','register','log','store'}) do assert(type(c[k])=='function') end
 local state='new';local count=0;local request,deadline,epoch,marker=nil,nil,nil,nil;local issuing=false
 local function fail() state='failed';return false end
 local function check()
  local t=c.clock();return type(t)=='number' and t==t and t>=0 and t<math.huge and (not deadline or t<deadline) and c.paused()==true
 end
 local api={}
 function api:begin(m)
  if state~='new' and state~='ready' then return fail() end
  if m~=nil and (type(m)~='string' or #m~=32 or not m:match('^[0-9a-f]+$')) then return fail() end
  if not check() then return fail() end
  count=count+1;if count>9007199254740991 then return fail() end
  request=c.nonce..':'..string.format('%.0f',count);marker=m;epoch=nil
  deadline=c.clock()+30;state='pending'
  issuing=true;local issued=c.issue('X4AuthorityShipRegistry','Status',{request_id=request});issuing=false
  if issued~=true or state~='pending' then return fail() end
  return true
 end
 function api:event(value)
  if issuing or state~='pending' or not check() or type(value)~='string' then return fail() end
  local req,kind,payload=value:match('^([0-9a-f]+:%d+)|([A-Za-z]+)|([^|]*)$')
  if req~=request then return fail() end
  if kind=='Epoch' then
   if epoch or #payload~=32 or not payload:match('^[0-9a-f]+$') then return fail() end
   epoch=payload;return true
  end
  local status
  if kind=='Uninitialized' and payload=='' and not epoch then status='uninitialized'
  elseif kind=='Count' and epoch and payload:match('^[1-9]%d*$') then
   local n=tonumber(payload)
   if not n or n>200000 or string.format('%.0f',n)~=payload then return fail() end
   status=epoch..'|'..payload
  else return fail() end
  if status~=c.expected or not check() then return fail() end
  state='delivering'
  if c.log(marker or 'startup',status)~=true or state~='delivering' or not check() then return fail() end
  if marker and c.store(marker)~=true then return fail() end
  if state~='delivering' or not check() then return fail() end
  marker=nil;deadline=nil;state='ready';return true
 end
 function api:tick()
  if state=='failed' or (state=='pending' and not check()) then return fail() end
  return true
 end
 function api:ready() return state=='ready' end
 assert(c.register(function(_,v) assert(api:event(v)) end)==true)
 return api
end
X4LAN_RECOVERY_REGISTRY_STATUS=M
return M
