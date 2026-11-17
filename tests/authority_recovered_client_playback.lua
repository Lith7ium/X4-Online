-- Actual recovered runtime/router/owner/binder/playback; fake X4 ABI and MD.
local ffi=require('ffi')
ffi.cdef[[void TestSetRecoveryCode(bool);int TestWrites(void);int TestReads(void);void TestPause(bool);void TestZone(uint64_t);]]
ffi.C.TestSetRecoveryCode(true)
local mode=arg[1]
local now=1
local events,requests,input,output,logs={},{},{},{},{}
function RegisterEvent(name,callback)assert(not events[name]);events[name]=callback;return true end
function GetCurRealTime()return now end
function AddUITriggeredEvent(screen,operation,arguments)requests[#requests+1]={screen=screen,args=arguments};return true end
function ConvertStringToLuaID(value)return ffi.new('uint64_t',tonumber(value))end
function ConvertIDTo64Bit(value)return value end
function GetComponentData(reference,...)
 local keys={...}
 if keys[1]=='isdocked' then return mode=='docking' and now>1.2,false,false end
 if keys[1]=='macro' and tonumber(reference)==41 then return mode=='fixture' and now>1.2 and 'wrong_macro' or 'ship_arg_m_trans_container_02_b_macro','antigone' end
 if keys[1]=='macro' and tonumber(reference)==43 then return 'cluster_06_sector001_macro' end
 error('unexpected read')
end
function DebugError(line)logs[#logs+1]=line end
function X4LAN_RECOVERED_CLIENT_LOAD_READY()return true end
local net={send=function(_,value)output[#output+1]=value;return true end,
 pending=function()return #input>0 end,receive=function()return table.remove(input,1)end}
package.loadlib=function()return function()return {open=function(_,port)assert(port==2345);return net end,monotonic=function()return now end}end end
X4LAN_LOCAL_UDP_MODULE=dofile('src/authority/lua/local_udp_module.lua')
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_REPLICA_MOTION_BINDING=dofile('src/authority/lua/replica_motion_binding.lua')
X4LAN_SAVED_BASELINE_MOTION_BINDING=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
X4LAN_MOTION_BUFFER=dofile('src/authority/lua/motion_buffer.lua')
X4LAN_SAVED_MOTION_APPLY=dofile('src/authority/lua/saved_motion_apply.lua')
X4LAN_MOTION_PLAYBACK=dofile('src/authority/lua/motion_playback.lua')
X4LAN_CLIENT_MOTION_EVENT_ROUTER=dofile('src/authority/lua/client_motion_event_router.lua')
X4LAN_MOTION_CLIENT_OWNER=dofile('src/authority/lua/motion_client_owner.lua')
local runtime=dofile('tools/dev/authority_recovered_client_motion.lua')
local lease,attempt,epoch,generation,nonce,router_generation=('a'):rep(32),('b'):rep(32),
 '4ba7be438ebb04ec5bb85fdb95b5a488',('d'):rep(32),('e'):rep(32),('9'):rep(32)
local configuration={enabled=true,port=2345,lease=lease,attempt=attempt,epoch=epoch,generation=generation,nonce=nonce,
 router_generation=router_generation,baseline=10082,index=1318,timeout=5,expected_save_path='/private/45841/save',
 saved_playback_fixture='recovery_enh_870'}
for _,change in ipairs({{index=1317},{epoch=('c'):rep(32)},{saved_playback_fixture='other'},
 {saved_apply_fixture='recovery_enh_870'}})do
 local invalid={};for key,value in pairs(configuration)do invalid[key]=value end
 for key,value in pairs(change)do invalid[key]=value end
 assert(not pcall(runtime.new_x4,invalid))
end
local client=assert(runtime.new_x4(configuration))
local function packet(sequence,x,source)
 return {'M',lease,attempt,'BIND',string.format('%032x',sequence+15),epoch,generation,'1318',tostring(sequence),
  'cluster_06_sector001_macro',('1'):rep(64),tostring(source),tostring(x),'0','0','-','-','-'}
end
local function send(sequence,x,source)
 input[1]=table.concat(packet(sequence,x,source),'|')
 assert(client:tick())
 local request=requests[#requests]
 assert(request.screen=='X4AuthoritySavedBaselineMotionBind')
 if mode=='paused_initial' and sequence==1 then ffi.C.TestPause(true) end
 events['X4AuthoritySavedBaselineMotionBind.Result'](nil,request.args.request_id..'|Bound|1318|0x29|0x2b')
end
send(1,1000000,0) -- Arbitrary first target is enrollment only and must never write.
if mode=='paused_initial' then
 assert(client:state()=='failed' and ffi.C.TestWrites()==0 and ffi.C.TestReads()==0)
 for _,line in ipairs(logs)do assert(not line:find(' INITIAL ',1,true))end
 return
end
assert(client:state()=='ready' and ffi.C.TestWrites()==0 and ffi.C.TestReads()>0)
assert(#logs==1 and logs[1]:find('AUTH_CLIENT_PLAYBACK INITIAL version=1 ',1,true))
assert(logs[1]:find(' x=0 y=0 z=0',1,true) and output[#output]:find('|BOUND|',1,true))
assert(client:tick() and ffi.C.TestWrites()==0)
if mode~='good' and mode~='bounded' and mode~='uncertain' and mode~='docking' and mode~='fixture' and mode~='zone' then
 local invalid=packet(2,5,.2)
 if mode=='sector' then invalid[10]='other_sector'
 elseif mode=='index' then invalid[8]='1317'
 elseif mode=='sequence' then invalid[9]='1'
 elseif mode=='source_time' then invalid[12]='0'
 elseif mode=='bind2' then invalid[4]='BIND2'
 elseif mode=='context' then invalid[7]=('f'):rep(32)
 else error('unknown mode')end
 input[1]=table.concat(invalid,'|')
 assert(not client:tick() and client:state()=='failed' and ffi.C.TestWrites()==0)
 return
end
now=1.2;send(2,5,.2);assert(client:tick() and ffi.C.TestWrites()==1)
if mode=='docking' or mode=='fixture' or mode=='zone' then
 now=1.3
 if mode=='zone' then ffi.C.TestZone(0)end
 assert(not client:tick() and client:state()=='failed' and ffi.C.TestWrites()==1)
 local expected='AUTH_RECOVERED_CLIENT_MOTION ERROR reason=owner_playback stage=read native_stage='..mode
 local found=false
 for _,line in ipairs(logs)do
  if line:find(expected,1,true)then found=true end
  for _,secret in ipairs({lease,attempt,generation,nonce,'wrong_macro','actor_key'})do assert(not line:find(secret,1,true))end
 end
 assert(found,'missing fixed original native failure stage')
 return
end
if mode=='bounded' then
 for sequence=3,150 do
  now=now+.6;send(sequence,sequence%2==0 and 5 or 6,sequence*.6)
  assert(client:tick())
 end
elseif mode=='good' then
 for tick=1,6 do now=1.2+tick*.1;assert(client:tick())end
 now=1.9;send(3,10,.9);assert(client:tick())
 for tick=1,16 do now=1.9+tick*.1;assert(client:tick())end
 assert(ffi.C.TestWrites()>=2)
end
input[1]=table.concat({'M',lease,attempt,'STOP',('8'):rep(32),epoch,generation},'|')
assert(client:tick() and client:state()=='stopped' and output[#output]:find('|STOPPED|',1,true))
local final=logs[#logs]
assert(final:find('AUTH_CLIENT_PLAYBACK STOPPED version=1 ',1,true))
if mode=='good' then assert(final:find(' uncertain=0 drained=1',1,true)) end
if mode=='uncertain' then assert(final:find(' uncertain=1 drained=0',1,true)) end
local summaries=0
for _,line in ipairs(logs)do
 assert(#line<=1024)
 if line:find(' SUMMARY ',1,true)then summaries=summaries+1 end
 for _,secret in ipairs({lease,attempt,generation,nonce,router_generation})do assert(not line:find(secret,1,true))end
 assert(not line:find('actor_key',1,true) and not line:find('sector_key',1,true) and not line:find('zone_key',1,true))
end
assert(summaries<=64 and #logs<=66)
if mode=='bounded' then assert(summaries==64) end
local count=#logs;ffi.C.TestPause(true);assert(client:tick() and #logs==count)
print('recovered playback initial read, streaming, bounded evidence and STOP passed')
