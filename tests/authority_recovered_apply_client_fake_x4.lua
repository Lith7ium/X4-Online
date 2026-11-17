-- Real recovery wrapper, UDP, owners and writer; X4 ABI and MD are simulated.
local ffi=require('ffi')
ffi.cdef[[int usleep(unsigned int); void TestAdvance(void); int TestWrites(void); void TestSetRecoveryCode(bool);]]
local actual_loadlib=package.loadlib
local library_path=assert(os.getenv('TEST_NET_LIB'))
local lib=assert(actual_loadlib(library_path,'luaopen_x4lan_net'))()
package.loadlib=function(path, symbol)
 assert(path=='./extensions/x4_lan_lab/native/x4lan_net.so' and symbol=='luaopen_x4lan_net')
 return actual_loadlib(library_path,symbol)
end
X4LAN_LOCAL_UDP_MODULE=dofile('src/authority/lua/local_udp_module.lua')
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
X4LAN_REPLICA_MOTION_BINDING=dofile('src/authority/lua/replica_motion_binding.lua')
X4LAN_SAVED_BASELINE_MOTION_BINDING=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
X4LAN_MOTION_BUFFER=dofile('src/authority/lua/motion_buffer.lua')
X4LAN_SAVED_MOTION_APPLY=dofile('src/authority/lua/saved_motion_apply.lua')
X4LAN_CLIENT_MOTION_EVENT_ROUTER=dofile('src/authority/lua/client_motion_event_router.lua')
X4LAN_MOTION_CLIENT_OWNER=dofile('src/authority/lua/motion_client_owner.lua')
local events,requests={},{}
local intent_digest
ffi.C.TestSetRecoveryCode(true)
function GetCurRealTime()return lib.monotonic()end
function RegisterEvent(name,callback)assert(not events[name]);events[name]=callback;return true end
function AddUITriggeredEvent(screen,op,args)
 requests[#requests+1]={screen=screen,op=op,args=args};return true
end
function ConvertStringToLuaID(value)return ffi.new('uint64_t',tonumber(value))end
function ConvertIDTo64Bit(value)return value end
function GetComponentData(ref,...)
 local args={...}
 if args[1]=='isdocked' then return false,false,false end
 if args[1]=='macro' and tonumber(ref)==41 then return 'ship_arg_m_trans_container_02_b_macro','antigone' end
 if args[1]=='macro' and tonumber(ref)==43 then return 'cluster_06_sector001_macro' end
 error('unexpected component query')
end
function X4LAN_RECOVERED_CLIENT_LOAD_READY()return true end
function DebugError(line)
 -- The real writer calls this immediately before its write. A missing or
 -- mismatched supervisor intent aborts the simulated write at its guard.
 local digest=line:match(' INTENT %S+ %d+ %d+ (%x+) ')
 if digest then
  assert(ffi.C.TestWrites()==0 and intent_digest==nil)
  local file=assert(io.open(assert(os.getenv('TEST_APPLY_INTENT')),'rb'))
  local record=file:read('*a');assert(file:close())
  assert(record:find('"sample_sha256":"'..digest..'"',1,true))
  assert(record:find('"index":1318',1,true) and record:find('"sequence":2',1,true))
  intent_digest=digest
 end
end
local module=dofile('tools/dev/authority_recovered_client_motion.lua')
local owner=assert(module.new_x4({enabled=true,port=tonumber(assert(os.getenv('TEST_NET_PORT'))),
 lease=('7'):rep(32),attempt=('b'):rep(32),epoch='4ba7be438ebb04ec5bb85fdb95b5a488',
 generation=('d'):rep(32),nonce=('e'):rep(32),router_generation=('9'):rep(32),
 timeout=5,baseline=10054,index=1318,expected_save_path='/private/45841/save',
 saved_apply_fixture='recovery_enh_870'}))
local advanced,reported=false,false
while true do
 while #requests>0 do
  local request=table.remove(requests,1)
  if request.screen=='X4AuthoritySavedBaselineMotionBind' then
   assert(request.op=='Bind' and request.args.index==1318)
   events['X4AuthoritySavedBaselineMotionBind.Result'](nil,request.args.request_id..'|Bound|1318|0x29|0x2b')
  elseif request.screen=='X4AuthoritySavedMotionApply' then
   assert(request.op=='Inspect' and request.args.index==1318)
   events['X4AuthoritySavedMotionApply.Result'](nil,request.args.request_id..'|ok')
  else error('unexpected simulated MD request')end
 end
 if ffi.C.TestWrites()>0 and not advanced then ffi.C.TestAdvance();advanced=true end
 assert(owner:tick(),'motion owner failed')
 if owner:state()=='stopped' and not reported then
  assert(ffi.C.TestWrites()==1 and intent_digest,'expected one simulated write after matching intent')
  local path=assert(os.getenv('TEST_APPLY_STOP_EVIDENCE'))
  local temporary=path..'.tmp'
  local file=assert(io.open(temporary,'wb'))
  assert(file:write('writes=1\ndigest='..intent_digest..'\n') and file:close())
  assert(os.rename(temporary,path))
  reported=true
 end
 ffi.C.usleep(1000)
end
