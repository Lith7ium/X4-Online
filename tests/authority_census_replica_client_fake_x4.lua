local ffi=require('ffi');ffi.cdef[[void test_context(bool);void test_pause(bool);]];local fake=ffi.load(assert(arg[1]),true)
local epoch,attempt,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32);local handlers,requests={},{};local count=0;local faulted=false;local dock=false
function RegisterEvent(name,cb)assert(not handlers[name]);handlers[name]=cb end
function AddUITriggeredEvent(screen,op,args)requests[#requests+1]={screen=screen,op=op,args=args};if op=='Create' then count=1 end;return true end
function GetCurRealTime()return 1 end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v)end
function ConvertStringToLuaID(v)local n=ffi.new('uint64_t',0);for d in v:gmatch('%d')do n=n*10+tonumber(d)end;return n end
function GetComponentData(_,a,b,c)if a=='macro' then return 'ship_a' end;assert(a=='isdocked' and b=='isdocking' and c=='isinternallystored');return dock,false,false end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_AUTHORITY_SHIP_ENGINE={new=function()return {fleet_count=function()return count end,fleet=function(_,cap)assert(cap==count+1);return count==0 and {} or {ffi.new('uint64_t',9007199254740992)+ffi.new('uint64_t',1)},false end}end}
local Driver=dofile('tools/dev/authority_census_replica_client.lua');local Adapter=dofile('tools/dev/authority_census_replica_client_x4.lua')
local d={version=1,type='job_descriptor',attempt=attempt,epoch=epoch,transport_sequence=1,job_sequence=7,index=10055,macro='ship_a',faction='argon',sector_macro='sector_a',x=1,y=2,z=3}
local w={epoch=epoch,index=41,sector_macro='sector_a',local_witness_match=true}
local owner=assert(Adapter.new({enabled=true,exclusive_events=true,driver=Driver,epoch=epoch,attempt=attempt,nonce=nonce,timeout=5,expected_save_path='/tmp/45841/save',guard=function()return true end,release_guard=function()return true end,fault=function()faulted=true end}))
assert(owner:start(d,w));handlers['X4AuthorityCensusReplica.Initialized'](nil,epoch)
for i=1,2 do handlers['X4AuthorityCensusReplica.Created'](nil,10055);handlers['X4AuthorityCensusReplica.Inspection'](nil,nonce..'-'..i..'|'..epoch..'|10055|0x20000000000001|0x2|sector_a') end
assert(not faulted and owner:state()=='intent_pending');assert(owner:tick());local ok,intent=owner:take_intent();assert(ok and intent.job_sequence==7 and intent.actor==nil)
handlers['X4AuthorityCensusReplica.Inspection'](nil,nonce..'-2|'..epoch..'|10055|0x20000000000001|0x2|sector_a');assert(faulted and owner:state()=='failed')
for _,kind in ipairs({'docked','pause','sector'})do
 handlers={};requests={};count=0;faulted=false;dock=false;fake.test_pause(true);fake.test_context(true)
 local n=assert(Adapter.new({enabled=true,exclusive_events=true,driver=Driver,epoch=epoch,attempt=attempt,nonce=nonce,timeout=5,expected_save_path='/tmp/45841/save',guard=function()return true end,release_guard=function()return true end,fault=function()faulted=true end}))
 assert(n:start(d,w));handlers['X4AuthorityCensusReplica.Initialized'](nil,epoch);handlers['X4AuthorityCensusReplica.Created'](nil,10055)
 if kind=='docked' then dock=true elseif kind=='pause' then fake.test_pause(false) else fake.test_context(false) end
 handlers['X4AuthorityCensusReplica.Inspection'](nil,nonce..'-1|'..epoch..'|10055|0x20000000000001|0x2|sector_a')
 assert(faulted and n:state()=='failed' and #requests==3,kind)
end
print('replica fake FFI passed')
