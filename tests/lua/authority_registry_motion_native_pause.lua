local ffi=require('ffi')
ffi.cdef[[void test_set_paused(bool);int test_writes(void);typedef uint64_t UniverseID;]]
local fake=ffi.load(assert(arg[1]),true)
local native=assert(loadfile('tools/dev/authority_registry_motion_native.lua'))()
local adapter=assert(loadfile('tools/dev/authority_registry_motion_probe.lua'))()
local continuous=assert(loadfile('src/authority/lua/fixture_continuous.lua'))()
local epoch=string.rep('a',32)
local requests=0
function ConvertIDTo64Bit(v) return v end
function ConvertStringToLuaID(v) return v end
function GetComponentData() return false,false,false end
function AddUITriggeredEvent() requests=requests+1 end
local wire={new=function(_,role,_,fixture)
 return {sent=0,step=function(self)
  self.sent=self.sent+1
  if role=='GUEST' then return {fixture=fixture,source_sequence=self.sent,x=10,y=0,z=0,vx=0,vy=0,vz=0} end
 end}
end}
local function new(role)
 return native.new({enabled=true,role=role,actor=ffi.new('UniverseID',1),epoch=epoch,index=1,frame='sectorA',
  expected_path='/tmp/45841/save',transport={},lease=string.rep('b',32),probe_module=adapter,
  wire_module=wire,continuous_module=continuous,clock=function() return 1 end,log=function() end,test_nudge=true})
end
local guest=new('GUEST');assert(requests==1);guest:verified(1);assert(fake.test_writes()==1)
guest:tick();assert(requests==2)
fake.test_set_paused(false)
assert(not pcall(function() guest:verified(1) end));assert(fake.test_writes()==1)
fake.test_set_paused(true);guest:tick();assert(requests==2) -- failed binding stays stopped
local source=new('SOURCE');source:verified(1);assert(fake.test_writes()==2) -- one controlled nudge
source:tick();local old=requests
fake.test_set_paused(false)
assert(not pcall(function() source:tick() end));assert(fake.test_writes()==2)
assert(not pcall(function() source:verified(1) end));assert(fake.test_writes()==2)
assert(requests==old)
assert(not pcall(function() new('GUEST') end));assert(requests==old) -- no request while unpaused
print('pause loss fences reads, writes, nudges and MD requests')
