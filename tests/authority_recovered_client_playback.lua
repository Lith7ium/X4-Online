-- Actual recovered runtime/router/owner/binder/playback; fake X4 ABI and MD.
local ffi=require('ffi')
ffi.cdef[[void TestSetRecoveryCode(bool);int TestWrites(void);int TestReads(void);void TestPause(bool);void TestZone(uint64_t);void TestDrift(float);]]
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
local error_observer
function DebugError(line)
 logs[#logs+1]=line
 if error_observer and line:find('AUTH_RECOVERED_CLIENT_MOTION ERROR',1,true)then error_observer()end
end
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
-- This mode exercises the actual wrapper/owner/playback composition with a
-- controllable native ownership adapter. MD behavior has separate tests.
local control_phase, control_preparations, control_releases = 'new', 0, 0
if mode == 'control' then
 configuration.saved_replica_control_fixture = 'recovery_enh_870'
 X4LAN_SAVED_REPLICA_CONTROL = {new_x4=function(options)
  assert(options.enabled == true and options.fixture == 'recovery_enh_870')
  assert(options.expected_save_path == configuration.expected_save_path)
  assert(options.resolve == X4LAN_RESOLVE_STRING and options.nonce == nonce)
  assert(options.binding.actor_key == '41' and options.binding.sector_key == '43')
  assert(options.binding.index == 1318 and options.binding.epoch == epoch)
  return {
   prepare=function()
    assert(options.guard() == true)
    control_preparations = control_preparations + 1
    control_phase = 'preparing'
    return true
   end,
   tick=function() return options.guard() == true end,
   state=function() return control_phase end,
   outcome_uncertain=function() return false end,
   release=function()
    assert(control_phase == 'prepared' and options.guard() == true)
    control_releases = control_releases + 1
    control_phase = 'releasing'
    return true
   end,
  }
 end}
end
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
 if mode == 'control' then
  assert(client:state() == 'preparing' and control_phase == 'preparing')
  assert(not output[#output]:find('|BOUND|', 1, true) or sequence > 1)
  if sequence == 1 then
   assert(ffi.C.TestWrites() == 0 and ffi.C.TestReads() == 0)
   assert(#logs == 0) -- INITIAL cannot be read or logged before preparation.
  end
  control_phase = 'prepared'
  assert(client:tick() and client:state() == 'ready')
 end
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
if mode~='good' and mode~='control' and mode~='bounded' and mode~='uncertain' and mode~='docking' and mode~='fixture' and mode~='zone' and mode~='distance' then
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
if mode=='distance' then
 now=1.3;ffi.C.TestDrift(100)
 local reads_at_error
 error_observer=function()
  reads_at_error=ffi.C.TestReads()
  ffi.C.TestDrift(999);now=50
  assert(not client:tick()) -- Reentry cannot change the captured failing observation.
  error('logger failed after changing native state')
 end
 assert(not client:tick() and client:state()=='failed' and ffi.C.TestWrites()==1)
 assert(reads_at_error and ffi.C.TestReads()==reads_at_error)
 assert(not client:tick())
 local failures=0
 for _,line in ipairs(logs)do
  if line:find('AUTH_CLIENT_PLAYBACK FAILURE ',1,true)then
   failures=failures+1;assert(#line<1024)
   local fields={}
   for key,value in line:gmatch('([%w_]+)=([^ ]+)')do fields[key]=value end
   assert(fields.version=='1' and fields.stage=='distance' and fields.phase=='held')
   assert(tonumber(fields.source_sequence)==2 and tonumber(fields.latest_source_time)==.2)
   assert(tonumber(fields.local_time)==1.3 and tonumber(fields.game_time)==10)
   assert(tonumber(fields.actual_x)==100 and tonumber(fields.target_x)==5)
   assert(tonumber(fields.actual_y)==0 and tonumber(fields.actual_z)==0)
   assert(tonumber(fields.target_y)==0 and tonumber(fields.target_z)==0)
   assert(tonumber(fields.correction_distance)==95 and fields.uncertain=='0')
   assert(fields.readbacks==nil) -- This is a pre-write observation, not a new readback.
   for _,secret in ipairs({lease,attempt,generation,nonce,'actor_key','logger failed'})do assert(not line:find(secret,1,true))end
  end
 end
 assert(failures==1)
 return
end
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
elseif mode=='good' or mode=='control' then
 for tick=1,6 do now=1.2+tick*.1;assert(client:tick())end
 now=1.9;send(3,10,.9);assert(client:tick())
 for tick=1,16 do now=1.9+tick*.1;assert(client:tick())end
 assert(ffi.C.TestWrites()>=2)
end
input[1]=table.concat({'M',lease,attempt,'STOP',('8'):rep(32),epoch,generation},'|')
if mode == 'control' then
 assert(client:tick() and client:state() == 'stopping')
 assert(control_preparations == 3 and control_releases == 1)
 assert(not output[#output]:find('|STOPPED|', 1, true))
 local writes_before_release = ffi.C.TestWrites()
 assert(client:tick() and client:state() == 'stopping')
 assert(ffi.C.TestWrites() == writes_before_release)
 control_phase = 'released'
end
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
