local ffi=require('ffi');ffi.cdef[[void test_pause(bool);]];local fake=ffi.load(assert(arg[1]),true)
local handlers={};local inbox,outbox={},{};local report,called=false,false;local epoch=string.rep('a',32);local attempt=string.rep('b',32);local lease=string.rep('c',32);local nonce=string.rep('d',32)
function RegisterEvent(n,cb)assert(not handlers[n]);handlers[n]=cb end
function GetCurRealTime()return 1 end
function AddUITriggeredEvent()return true end
function Pause()fake.test_pause(true)end
function Unpause()fake.test_pause(false)end
function DebugError()end
local old=package.loadlib;package.loadlib=function(path,sym)assert(path=='./extensions/x4_lan_lab/native/x4lan_net.so' and sym=='luaopen_x4lan_net');return function()return {open=function(host,port)assert(host=='127.0.0.1' and port==3456);return {send=function(_,v)outbox[#outbox+1]=v;return true end,receive=function()return table.remove(inbox,1)end,close=function()end}end}end end
local H={new_x4=function(o)report=o.report;return {start=function()return true end,state=function()return 'waiting' end,tick=function()if not called then called=true;return true,'attached_wait_running' end;assert(report({epoch=epoch,index=10055,sequence=2,classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false},ffi.new('uint64_t',9007199254740992)+ffi.new('uint64_t',1)));return true,'waiting'end}end}
local D={new_x4=function()return {start=function()return true end,tick=function()return true end,close=function()return true end,response=function(_,v)assert(v=='d');return true,{epoch=epoch,index=10055,sequence=2,macro='ship_a',owner='argon',sector_macro='sector_a',x=1,y=2,z=3}end}end}
local W={new_x4=function(o)assert(o.index==41);return {start=function()return true end,tick=function()return true end,close=function()return true end,response=function(_,v)assert(v=='w');return true,{epoch=epoch,index=41,sector_macro='sector_a',local_witness_match=true}end}end}
local O=dofile('tools/dev/authority_census_job_owner.lua');local X=dofile('tools/dev/authority_census_job_owner_x4.lua')
local app=assert(X.new({enabled=true,role='server',epoch=epoch,attempt=attempt,lease=lease,nonce=nonce,timeout=100,window=30,port=3456,expected_save_path='/tmp/45841/save',guard=function()return true end,owner=O,host=H,probe={},descriptor=D,descriptor_core={},witness=W}))
assert(app:tick() and app:state()=='ready');local prefix=table.concat({'CMD',lease,'server',attempt,epoch},'|');inbox[1]=prefix..'|START';assert(app:tick());assert(app:tick() and app:state()=='captured');assert(app:tick());assert(app:tick());assert(app:tick() and app:state()=='descriptor_wait')
handlers['X4AuthorityPausedJobDescriptor.Result'](nil,'d');assert(app:tick() and app:state()=='descriptor_sent');inbox[1]=prefix..'|WITNESS|2|41|sector_a';assert(app:tick());handlers['X4AuthoritySectorWitnessRuntime.Result'](nil,'w');assert(app:tick() and app:state()=='finished')
for _,p in ipairs(outbox)do assert(not p:find('20000000000001',1,true))end
assert(app:close());handlers={};inbox={};outbox={};fake.test_pause(true)
local client=assert(X.new({enabled=true,role='client',epoch=epoch,attempt=attempt,lease=lease,nonce=nonce,timeout=100,window=30,port=3456,expected_save_path='/tmp/45841/save',guard=function()return true end,owner=O,host=H,probe={},descriptor=D,descriptor_core={},witness=W}))
assert(client:tick() and #outbox==0 and client:state()=='client_baseline');handlers['X4AuthorityCensusJobBaseline.Result'](nil,nonce..'|'..epoch..'|10054|ok');assert(client:tick() and client:state()=='ready' and #outbox==1)
local clientprefix=table.concat({'CMD',lease,'client',attempt,epoch},'|');inbox[1]=clientprefix..'|WITNESS|2|41|sector_a';assert(client:tick());handlers['X4AuthoritySectorWitnessRuntime.Result'](nil,'w');assert(client:tick() and client:state()=='finished');assert(client:close());package.loadlib=old
print('census owner fake X4 passed')
