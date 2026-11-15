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
print('fake X4 host conversion checks passed')
