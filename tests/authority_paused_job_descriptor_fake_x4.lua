local ffi=require('ffi');ffi.cdef[[void test_context(bool);void test_pause(bool);]];local fake=ffi.load(assert(arg[1]),true)
local epoch,rid=string.rep('a',32),string.rep('b',32);local issued={};local dock=false
function AddUITriggeredEvent(screen,op,args)issued[#issued+1]={screen=screen,args=args} end
function GetCurRealTime()return 1 end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v)end
function ConvertStringToLuaID(v)local n=ffi.new('uint64_t',0);for digit in v:gmatch('%d') do n=n*10+tonumber(digit) end;return n end
function GetComponentData(_,a,b,c)assert(a=='isdocked' and b=='isdocking' and c=='isinternallystored');return dock,false,false end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local P=dofile('tools/dev/authority_paused_job_descriptor.lua');local Core=dofile('tools/dev/authority_job_descriptor_probe.lua')
local id=ffi.new('uint64_t',9007199254740992)+ffi.new('uint64_t',1)
local cfg={enabled=true,core=Core,epoch=epoch,request_id=rid,timeout=5,actor=id,expected_save_path='/tmp/45841/save',
 row={epoch=epoch,index=2,sequence=1,classification='new_registry_entry'},guard=function()return true end}
local function result()return rid..'|'..epoch..'|2|ok|0x20000000000001|ship_a|argon|0x2|sector_a'end
local p=P.new_x4(cfg);assert(p:start());assert(issued[1].screen=='X4AuthorityPausedJobDescriptor');local ok,row=p:response(result());assert(ok and row.x==1 and row.paused_checks_passed and row.sector_local==nil)
issued={};dock=true;p=P.new_x4(cfg);assert(p:start());assert(not p:response(result()));dock=false
fake.test_context(false);p=P.new_x4(cfg);assert(p:start());assert(not p:response(result()));fake.test_context(true)
fake.test_pause(false);issued={};p=P.new_x4(cfg);assert(not p:start() and #issued==0);fake.test_pause(true)
cfg.actor=9007199254740992;issued={};p=P.new_x4(cfg);assert(not p:start() and #issued==0)
print('fake X4 paused descriptor passed')
