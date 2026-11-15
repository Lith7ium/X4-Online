-- Local read-only 12-fixture diagnostic. No X4 calls, ownership decisions,
-- socket creation, expiry clock or game writes. See AUTHORITY-FLEET-DIAGNOSTIC.
local M = {}
local MAX = 9007199254740991
local function identity(v)
 return type(v)=='string' and #v>0 and #v<=64 and v:match('^[A-Za-z0-9_.%-]+$')~=nil
end
local function finite(v)
 return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge
end
local function sequence(s)
 if type(s)~='string' or #s>16 or not s:match('^[1-9]%d*$') then return nil end
 local n=tonumber(s)
 if not n or n>MAX or string.format('%.0f',n)~=s then return nil end
 return n
end
local function decimal(s)
 if type(s)~='string' then return nil end
 local mantissa, exponent=s:match('^([^eE]+)[eE]([+-]?%d+)$')
 if not mantissa then
  if s:find('[eE]') then return nil end
  mantissa=s
 end
 mantissa=mantissa:gsub('^[+-]', '')
 if not mantissa:match('^%d+%.?%d*$') and not mantissa:match('^%.%d+$') then return nil end
 local n=tonumber(s)
 if not finite(n) then return nil end
 return n
end
function M.new(transport, role, lease, fixtures, max_reply_age)
 assert((type(transport)=='table' or type(transport)=='userdata') and
  type(transport.send)=='function' and type(transport.receive)=='function', 'transport required')
 assert(role=='SOURCE' or (type(role)=='string' and role:match('^GUEST[1-8]$')), 'invalid role')
 assert(type(lease)=='string' and #lease==32 and lease:match('^[0-9a-f]+$'), 'invalid lease')
 assert(type(fixtures)=='table', 'fixture mapping required')
 if role~='SOURCE' then
  assert(finite(max_reply_age) and max_reply_age>0 and max_reply_age<=60, 'guest reply age required')
 end
 local frames, ids, sent, received, source_received, outstanding={},{},{},{},{},{}
 local last_now=nil
 for id,frame in pairs(fixtures) do
  assert(identity(id) and identity(frame), 'invalid identity or frame')
  frames[id]=frame; ids[#ids+1]=id; sent[id]=0; received[id]=0; source_received[id]=0; outstanding[id]={}
 end
 assert(#ids==12, 'exactly 12 fixture/frame pairs required')
 table.sort(ids)
 local state={ready=false}
 local function send(data)
  assert(#data<=512 and transport:send(data)==true, 'fleet datagram send failed')
 end
 local function next_seq(id)
  assert(sent[id]<MAX, 'sequence exhausted')
  sent[id]=sent[id]+1
  return string.format('%.0f',sent[id])
 end
 function state:step(samples, now)
  if role=='SOURCE' then
   assert(type(samples)=='table', 'source samples required')
   for id,p in pairs(samples) do
    assert(frames[id] and type(p)=='table' and finite(p.x) and finite(p.y) and finite(p.z), 'invalid source sample')
   end
  else
   assert(samples==nil, 'guests cannot publish samples')
   assert(finite(now) and now>=0 and (not last_now or now>=last_now), 'monotonic clock required')
   last_now=now
  end
  if not self.ready then send('FLEET1|HELLO|'..role..'|'..lease) end
  local updates, emitted={},{}
  for _=1,64 do
   local packet=transport:receive()
   if not packet then break end
   if type(packet)=='string' and #packet<=512 then
    if packet=='FLEET1|READY|'..role then
     self.ready=true
    elseif self.ready and role~='SOURCE' then
     local id,frame,request,source,x,y,z=packet:match('^FLEET1|POS|([A-Za-z0-9_.%-]+)|([A-Za-z0-9_.%-]+)|(%d+)|(%d+)|([^|]+)|([^|]+)|([^|]+)$')
     request,source=sequence(request),sequence(source)
     x,y,z=decimal(x),decimal(y),decimal(z)
     local issued=id and request and outstanding[id] and outstanding[id][request]
     if id and frames[id]==frame and request and source and issued and now-issued<=max_reply_age and
        request>received[id] and source>source_received[id] and x and y and z then
      outstanding[id][request]=nil
      received[id],source_received[id]=request,source
      updates[#updates+1]={fixture=id,frame=frame,request=request,source_sequence=source,x=x,y=y,z=z}
     end
    end
   end
  end
  if self.ready then
   for _,id in ipairs(ids) do
    if role=='SOURCE' then
     local p=samples[id]
     if p then
      local seq=next_seq(id)
      send(table.concat({'FLEET1','PUT',lease,id,frames[id],seq,
       string.format('%.17g',p.x),string.format('%.17g',p.y),string.format('%.17g',p.z)},'|'))
      emitted[#emitted+1]={fixture=id, sequence=tonumber(seq)}
     end
    else
     local request=next_seq(id)
     local n=sent[id]
     outstanding[id][n]=now
     outstanding[id][n-64]=nil
     send(table.concat({'FLEET1','GET',lease,id,frames[id],request},'|'))
    end
   end
  end
  return updates, emitted
 end
 return state
end
return M
