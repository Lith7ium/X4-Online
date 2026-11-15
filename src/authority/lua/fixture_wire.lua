-- One-fixture, local diagnostic protocol. No X4 calls or socket is opened here.
-- The caller supplies the existing nonblocking x4lan_net transport and an
-- enrolled pose. This is not the Internet protocol or gameplay replication.
local M = {}
local MAX_SEQUENCE = 9007199254740991

local function finite(x)
 return type(x)=='number' and x==x and x~=math.huge and x~=-math.huge
end
local function sequence(s)
 if type(s)~='string' or not s:match('^[1-9]%d*$') or #s>16 then return nil end
 local n=tonumber(s)
 if not n or n>MAX_SEQUENCE or string.format('%.0f',n)~=s then return nil end
 return n
end
local function identity(value)
 return type(value)=='string' and #value>0 and #value<=64 and value:match('^[%w_.%-]+$')~=nil
end

function M.new(transport, role, lease, fixture, motion)
 assert((type(transport)=='table' or type(transport)=='userdata') and
  type(transport.send)=='function' and type(transport.receive)=='function', 'transport required')
 assert(role=='SOURCE' or role=='GUEST', 'invalid fixture role')
 assert(type(lease)=='string' and #lease==32 and lease:match('^[0-9a-f]+$'), 'invalid test lease')
 assert(identity(fixture), 'invalid fixture')
 local state={ready=false, sent=0, received_request=0, received_source=0}
 local function send(text)
  assert(#text<=512 and transport:send(text)==true, 'diagnostic datagram send failed')
 end
 local function next_seq()
  assert(state.sent<MAX_SEQUENCE, 'fixture sequence exhausted')
  state.sent=state.sent+1
  return string.format('%.0f',state.sent)
 end
 function state:step(position)
  -- Every retry uses the same role and lease; the adapter only permits the
  -- original endpoint. A lost READY must not strand the test.
  if not self.ready then send('FIX1|HELLO|'..role..'|'..lease..'|'..fixture) end
  local latest
  for _=1,16 do
   local packet=transport:receive()
   if not packet then break end
   if type(packet)=='string' and #packet<=512 then
    if packet=='FIX1|READY|'..role..'|'..fixture then
     self.ready=true
    elseif self.ready and role=='GUEST' then
     local id,request,source,x,y,z,vx,vy,vz=packet:match('^FIX1|POS|([%w_.%-]+)|(%d+)|(%d+)|([^|]+)|([^|]+)|([^|]+)|([^|]+)|([^|]+)|([^|]+)$')
     local hasrate=id~=nil
     if not id then id,request,source,x,y,z=packet:match('^FIX1|POS|([%w_.%-]+)|(%d+)|(%d+)|([^|]+)|([^|]+)|([^|]+)$') end
     if vx then vx,vy,vz=tonumber(vx),tonumber(vy),tonumber(vz) end
     request,source=sequence(request),sequence(source)
     x,y,z=tonumber(x),tonumber(y),tonumber(z)
     if id==fixture and request and source and request<=self.sent and
        request>self.received_request and source>self.received_source and finite(x) and finite(y) and finite(z) and (not hasrate or (finite(vx) and finite(vy) and finite(vz))) then
      self.received_request,self.received_source=request,source
      latest={fixture=fixture, request=request, source_sequence=source, x=x, y=y, z=z, vx=vx, vy=vy, vz=vz}
     end
    end
   end
  end
  if self.ready then
   if role=='SOURCE' then
    assert(type(position)=='table' and finite(position.x) and finite(position.y) and finite(position.z), 'finite source pose required')
    local payload=table.concat({'FIX1','PUT',lease,fixture,next_seq(),
     string.format('%.17g',position.x),string.format('%.17g',position.y),string.format('%.17g',position.z)},'|')
    if motion and position.vx then
     assert(finite(position.vx) and finite(position.vy) and finite(position.vz), 'finite estimated rate required')
     payload=payload..string.format('|%.17g|%.17g|%.17g',position.vx,position.vy,position.vz)
    end
    send(payload)
   else
    send(table.concat({'FIX1','GET',lease,fixture,next_seq()},'|'))
   end
  end
  return latest
 end
 return state
end

X4LAN_AUTHORITY_FIXTURE_WIRE=M
return M
