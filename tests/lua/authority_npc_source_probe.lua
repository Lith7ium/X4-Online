local ffi=require('ffi');ffi.cdef[[void test_state(bool,float,double);]]
local fake=ffi.load(assert(arg[1]),true)
local epoch,lease=string.rep('a',32),string.rep('b',32)
local events,update={},nil
local variant=arg[2];local guards=0
local real=0;local command='NPCCMD|'..lease..'|ARM|sectorA'
local logs,sent={},{}
X4LAN_CONFIG={authority_npc_flight_source=true,test_profile='45841',authority_create_epoch=epoch,
 authority_npc_lease=lease,authority_npc_port=1,authority_motion_port=2,
 authority_motion_lease=string.rep('c',32),authority_motion_save_path='/tmp/45841/save'}
function RegisterEvent(name,cb) events[name]=cb end
function SetScript(_,cb) update=cb end
function DebugError(line) logs[#logs+1]=line end
function ConvertIDTo64Bit(v) return v end
function ConvertStringToLuaID(v) return v end
function GetComponentData() return false,false,false end
local control={send=function(_,v) sent[#sent+1]=v;return true end,
 receive=function() local v=command;command=nil;return v end}
local relay={close=function() end};local opens=0
package.loadlib=function() return function() return {open=function() opens=opens+1;return opens==1 and control or relay end,
 monotonic=function() return real end} end end
X4LAN_AUTHORITY_FIXTURE_WIRE={new=function(_,role,_,fixture,motion)
 assert(role=='SOURCE' and fixture==epoch..'.1.sectorA' and motion)
 return {sent=0,step=function(self,p) assert(p and p.x);self.sent=self.sent+1 end}
end}
local function event(name,value) assert(events[name],name);events[name](nil,value) end
function AddUITriggeredEvent(screen,op,_)
 if screen=='X4AuthorityNPCFlightFixture' and op=='Order' then
  event(screen..'.Pilot',99);event(screen..'.OrderId','MoveWait');event(screen..'.GameTime',0);event(screen..'.Ready',1)
 elseif screen=='X4AuthorityNPCFlightGuard' and op=='Validate' then
  guards=guards+1;event(screen..'.Verified',variant=='changed-actor' and guards>1 and 9 or 1)
 else error('unexpected '..screen..'.'..op) end
end
fake.test_state(true,0,0)
assert(loadfile('tools/dev/authority_npc_flight_source.lua'))();update()
assert(sent[#sent]=='NPCRESULT|'..lease..'|ARMED|sectorA')
fake.test_state(false,0,1);real=1;update()
if variant=='pause-and-stop' then
 local before=#sent
 fake.test_state(true,10,2);real=2;command='NPCCMD|'..lease..'|STOP|';update()
 -- The update can send an ordinary HELLO, but must never confirm STOPPED.
 for i=before+1,#sent do assert(not sent[i]:find('|STOPPED',1,true)) end
 assert(logs[#logs]:find('ERROR',1,true));return
end
if variant=='pause-loss' then
 fake.test_state(true,10,2);real=2;update()
 local before=#sent;command='NPCCMD|'..lease..'|STOP|';update();assert(#sent==before)
 assert(logs[#logs]:find('ERROR',1,true));return
end
fake.test_state(false,10,2);real=2;update()
if variant=='changed-actor' then
 assert(logs[#logs]:find('ERROR',1,true));local before=#sent
 command='NPCCMD|'..lease..'|STOP|';update();assert(#sent==before);return
end
local observed
for _,line in ipairs(logs) do if line:find(' SAMPLE ',1,true) then observed=line end end
assert(observed and observed:find('x=10 ',1,true) and observed:find('vx=10 ',1,true)
 and observed:find('reference_real_time=1 ',1,true) and observed:find('reference_x=0 ',1,true),tostring(observed))
command='NPCCMD|'..lease..'|STOP|';real=2.1;update()
assert(sent[#sent]=='NPCRESULT|'..lease..'|STOPPED')
print('source samples actual reference and stops')
