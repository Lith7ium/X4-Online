local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
local handlers,requests,inbox,outbox,logs={},{},{},{},{};local count=0
local lease,attempt,epoch,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32)
function RegisterEvent(name,cb)assert(not handlers[name]);handlers[name]=cb end
function AddUITriggeredEvent(screen,op,args)requests[#requests+1]={screen=screen,op=op,args=args};if screen=='X4AuthorityCensusReplica' and op=='Create' then count=1 end;return true end
function GetCurRealTime()return 1 end
function Pause()end function Unpause()end
function DebugError(v)logs[#logs+1]=v end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v)end
function ConvertStringToLuaID(v)local n=ffi.new('uint64_t',0);for d in v:gmatch('%d')do n=n*10+tonumber(d) end;return n end
function GetComponentData(_,a,b,c)if a=='macro' then return 'ship_a' end;assert(a=='isdocked' and b=='isdocking' and c=='isinternallystored');return false,false,false end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_AUTHORITY_SHIP_ENGINE={new=function()return {fleet_count=function()return count end,fleet=function(_,cap)assert(cap==count+1);return count==0 and {} or {ffi.new('uint64_t',9007199254740992)+ffi.new('uint64_t',1)},false end}end}
local previous=package.loadlib;package.loadlib=function(path,sym)assert(path=='./extensions/x4_lan_lab/native/x4lan_net.so');return function()return {open=function(host,port)assert(host=='127.0.0.1');return {send=function(_,v)outbox[#outbox+1]=v;return true end,receive=function()return table.remove(inbox,1)end,close=function()end}end}end end
local base=dofile('tools/dev/authority_census_job_owner.lua');local base_x4=dofile('tools/dev/authority_census_job_owner_x4.lua');local driver=dofile('tools/dev/authority_census_replica_client.lua');local adapter=dofile('tools/dev/authority_census_replica_client_x4.lua');local wrap=dofile('tools/dev/authority_census_replica_udp.lua')
local witness={new_x4=function(o)return {start=function()return true end,tick=function()return true end,close=function()return true end,response=function()return true,{epoch=epoch,index=o.index,sector_macro=o.macro,local_witness_match=true}end}end}
local app=assert(wrap.new_x4({enabled=true,role='client',epoch=epoch,attempt=attempt,lease=lease,nonce=nonce,timeout=100,window=30,port=3456,expected_save_path='/tmp/45841/save',guard=function()return true end,
 base_adapter=base_x4,base_owner=base,replica_adapter=adapter,replica_driver=driver,host={},probe={},descriptor={},descriptor_core={},witness=witness}))
assert(app:tick());handlers['X4AuthorityCensusJobBaseline.Result'](nil,nonce..'|'..epoch..'|10054|ok');assert(app:tick() and outbox[#outbox]:match('|READY$'))
local prefix=table.concat({'CMD',lease,'client',attempt,epoch},'|');inbox[1]=prefix..'|WITNESS|2|41|sector_a';assert(app:tick());handlers['X4AuthoritySectorWitnessRuntime.Result'](nil,'ok');assert(app:tick() and outbox[#outbox]:match('|WITNESS_READY|2|41|sector_a$'))
inbox[1]=prefix..'|REPLICA|2|10055|ship_a|argon|sector_a|1|2|3';assert(app:tick());handlers['X4AuthorityCensusReplica.Initialized'](nil,epoch)
for i=1,2 do handlers['X4AuthorityCensusReplica.Created'](nil,10055);handlers['X4AuthorityCensusReplica.Inspection'](nil,nonce..'-'..i..'|'..epoch..'|10055|0x20000000000001|0x2|sector_a') end
assert(app:tick() and app:state()=='intent_pending');assert(app:tick() and app:state()=='finished' and outbox[#outbox]:match('|WITNESS_OK|2|41|sector_a$'))
assert(logs[#logs-1]:match('AUTH_CENSUS_REPLICA DONE$') and logs[#logs]:match('AUTH_CENSUS_JOB WITNESS_OK$'));assert(app:close());package.loadlib=previous
print('full replica binding fake X4 passed')
