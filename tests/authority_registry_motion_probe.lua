local make=assert(loadfile('tools/dev/authority_registry_motion_probe.lua'))()
local wire=assert(loadfile('src/authority/lua/fixture_wire.lua'))()
local continuous=assert(loadfile('src/authority/lua/fixture_continuous.lua'))()
local epoch=string.rep('a',32)
local time=0
local server={x=0,y=0,z=0}
local client={x=-20,y=0,z=0}
local latest,source,guest,good,writes=nil,nil,nil,true,0
local logs={}
local function transport(role)
 local queue={}
 return {
  send=function(_,packet)
   local p={};for field in packet:gmatch('[^|]+') do p[#p+1]=field end
   if p[2]=='HELLO' then queue[#queue+1]='FIX1|READY|'..role..'|'..p[5]
   elseif p[2]=='PUT' then latest={fixture=p[4],seq=p[5],x=p[6],y=p[7],z=p[8],vx=p[9],vy=p[10],vz=p[11]}
   elseif p[2]=='GET' and latest then
    local pos=table.concat({'FIX1','POS',latest.fixture,p[5],latest.seq,latest.x,latest.y,latest.z},'|')
    if latest.vx then pos=pos..'|'..latest.vx..'|'..latest.vy..'|'..latest.vz end
    queue[#queue+1]=pos
   end
   return true
  end,
  receive=function() return table.remove(queue,1) end,
 }
end
local function create(role,actor)
 local resolved=false
 local o={enabled=true,role=role,epoch=epoch,index=1,frame='sectorA',lease=string.rep(role=='SOURCE' and 'b' or 'c',32),
  transport=transport(role),wire_module=wire,continuous_module=continuous,
  resolve=function(e,i) assert(e==epoch and i==1);resolved=true end,
  validate=function(a,e,i,f) return good and a==actor and e==epoch and i==1 and f=='sectorA' end,
  read=function(a) assert(a==actor);return actor end,
  write=function(a,f,target) assert(a==client and f=='sectorA');writes=writes+1;a.x=target.x;a.y=target.y;a.z=target.z end,
  clock=function() return time end,log=function(v) logs[#logs+1]=v end}
 local probe=make.new(o);assert(resolved)
 probe:bind(epoch,1,actor)
 return probe
end
source=create('SOURCE',server);guest=create('GUEST',client)
source:step();guest:step()
time=.1;server.x=1;source:step();guest:step()
time=.2;server.x=2;source:step();guest:step()
assert(writes==1 and math.abs(client.x-2)<.0001) -- 1m + 10m/s * 0.1s
assert(latest.vx and tonumber(latest.vx)==10)
-- Old, velocity-less observation is unknown and must not move the guest.
time=2;source:step();guest:step()
time=2.1;guest:step();assert(writes==2) -- previous valid reply, new reply remains queued
local before=writes
time=2.2;guest:step();assert(writes==before)
-- A changed frame, registry binding, lifetime or safety proof prevents writes.
good=false
assert(not pcall(function() guest:step() end));assert(writes==before)
good=true;assert(not pcall(function() guest:step() end)) -- failed guard latches stop
assert(#logs>0)
print('registry motion probe test passed')
