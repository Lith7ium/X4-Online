local ffi=require('ffi')
ffi.cdef[[void test_state(bool,float,double);]]
local fake=ffi.load(assert(arg[1]),true);fake.test_state(false,0,1)
local handlers,requests={},{}
function RegisterEvent(name,cb) handlers[name]=cb end
function AddUITriggeredEvent(screen,op,args) requests[#requests+1]={screen=screen,op=op,args=args} end
function ConvertIDTo64Bit(v) return ffi.new('uint64_t',assert(v.raw or v.md)) end
function ConvertStringToLuaID(v) assert(v=='1');return {md=tonumber(v)} end
function GetCurRealTime() return 1 end
local host=dofile('tools/dev/authority_job_registry_host.lua')
local probe=dofile('tools/dev/authority_job_registry_probe.lua')
local raw={raw=1}
local app=host.new_x4({enabled=true,expected_save_path='/tmp/45841/save',epoch=string.rep('a',32),
 baseline={raw},capacity=4,window=1,timeout=2,probe=probe,
 report=function() return true end,done=function() return true end,fault=function(e) error(e) end})
assert(app:start());handlers['X4AuthorityShipRegistry.Initialized'](nil,string.rep('a',32))
assert(requests[2].op=='Enroll' and requests[2].args.ship~=raw and requests[2].args.ship.md==1)
-- Existing register attach is possible only while the fake X4 is paused.
handlers,requests={},{};fake.test_state(true,0,1)
local fault
local attached=host.new_x4({enabled=true,expected_save_path='/tmp/45841/save',epoch=string.rep('a',32),
 baseline={},attach_saved_registry=true,exclusive_registry_consumer=true,expected_last=10054,
 capacity=4,window=1,timeout=2,probe=probe,
 report=function() return true end,done=function() return true end,fault=function(e) fault=e end})
assert(attached:start() and requests[1].op=='Status')
handlers['X4AuthorityShipRegistry.Epoch'](nil,string.rep('a',32))
handlers['X4AuthorityShipRegistry.Count'](nil,10054)
assert(requests[2].screen=='X4AuthorityJobShipEvents' and requests[2].op=='Status')
handlers['X4AuthorityJobShipEvents.Uninitialized'](nil,nil)
assert(requests[3].op=='Initialize')
handlers['X4AuthorityJobShipEvents.Initialized'](nil,string.rep('a',32))
assert(attached:state()=='attached_wait_running')
fake.test_state(false,0,2);assert(attached:tick())
assert(requests[4].screen=='X4AuthorityJobShipEvents' and requests[4].op=='Status' and not fault)
-- The opt-in external context fence must run for asynchronous MD callbacks.
handlers,requests={},{};fake.test_state(true,0,1)
local allowed=true;local context_fault
local guarded=host.new_x4({enabled=true,expected_save_path='/tmp/45841/save',epoch=string.rep('a',32),
 baseline={},attach_saved_registry=true,exclusive_registry_consumer=true,expected_last=10054,
 capacity=4,window=1,timeout=2,probe=probe,context_guard=function()return allowed end,
 report=function()return true end,done=function()return true end,fault=function(e)context_fault=e end})
assert(guarded:start() and #requests==1);allowed=false
handlers['X4AuthorityShipRegistry.Epoch'](nil,string.rep('a',32))
assert(context_fault=='context_guard' and #requests==1)
-- A raw actor guard refuses before an Enroll can be emitted.
handlers,requests={},{};fake.test_state(false,0,1)
local raw_refused
local raw_guarded=host.new_x4({enabled=true,expected_save_path='/tmp/45841/save',epoch=string.rep('a',32),
 baseline={raw},capacity=4,window=1,timeout=2,probe=probe,context_guard=function()return true end,
 raw_actor_guard=function()return false end,report=function()return true end,done=function()return true end,
 fault=function(e)raw_refused=e end})
assert(raw_guarded:start());handlers['X4AuthorityShipRegistry.Initialized'](nil,string.rep('a',32))
assert(raw_refused)
for _,r in ipairs(requests)do assert(r.op~='Enroll')end
print('fake X4 host conversion checks passed')
