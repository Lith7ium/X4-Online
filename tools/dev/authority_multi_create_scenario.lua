-- One isolated, opt-in native probe scenario. The caller owns the update hook.
local M={}
function M.new(o)
 assert(type(o)=='table' and o.enabled==true and type(o.client)=='table')
 for _,k in ipairs({'clock','guard','issue','inspect','emit'}) do assert(type(o[k])=='function') end
 assert(type(o.descriptors)=='table' and #o.descriptors==2)
 local d=o.descriptors
 assert(d[1].index==o.baseline+1 and d[2].index==o.baseline+2 and d[1].sector~=d[2].sector)
 local expected={'initialize','create','create','replay','replay'}
 local indices={false,d[1].index,d[2].index,d[1].index,d[2].index}
 local sectors={false,d[1].sector,d[2].sector,d[1].sector,d[2].sector}
 local phase=0;local delivered=nil;local done=false;local failed=false;local settle=nil;local client
 local function fail() failed=true;return false end
 client=assert(o.client.new({enabled=true,epoch=o.epoch,nonce=o.nonce,baseline=o.baseline,timeout=o.timeout,
  clock=o.clock,guard=o.guard,issue=o.issue,inspect=o.inspect,
  complete=function(kind,result)
   if failed or delivered or kind~=expected[phase] then return fail() end
   if kind=='initialize' then if result.epoch~=o.epoch then return fail() end
   elseif result.index~=indices[phase] then return fail() end
   delivered=kind;return true
  end}))
 local api={}
 function api:event(value)
  if failed or done or delivered then return fail() end
  if not client:event(value) then return fail() end
  if delivered then
   if not o.guard() then return fail() end
   if phase>1 then o.emit('ROW '..delivered..' '..indices[phase]..' '..sectors[phase]) end
   delivered=nil;phase=phase+1
  end
  return true
 end
 function api:tick()
  if failed then return false end
  if not o.guard() or not client:tick() then return fail() end
  if done then return true end
  if phase==0 then phase=1;return client:initialize() or fail() end
  if phase>=2 and phase<=5 and client:state()=='ready' then
   local i=(phase==2 or phase==4) and 1 or 2
   return client:create(d[i]) or fail()
  end
  if phase==6 then
   local now=o.clock();if not settle then settle=now end
   if now<settle then return fail() end
   if now-settle>=0.5 then o.emit('DONE');done=true end
  end
  return true
 end
 return api
end
return M
