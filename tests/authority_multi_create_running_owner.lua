local ffi=require('ffi')
ffi.cdef[[void TestReset(void);void TestUnpause(void);void TestPause(void);void TestAdvance(double);]]
local actual_client=dofile('tools/dev/authority_multi_create_client.lua')
local use_real=os.getenv('RUNNING_REAL_INSPECTOR')=='1'
local real_inspector=use_real and dofile('src/authority/lua/x4_multi_create_inspector.lua')
local real_resolve=use_real and dofile('tools/dev/authority_registry_resolve_string.lua')
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local function scenario(mode)
 ffi.C.TestReset();local callback,packets,logs=nil,{},{};local now=1;local arms=0
 X4LAN_CONFIG={authority_multi_create_running=true,authority_load_save_path='/private/45841/save',
  authority_multi_create_timeout=30,authority_multi_create_epoch=epoch,authority_multi_create_nonce=nonce,
  authority_multi_create_baseline=10054,authority_multi_create_sector1='sector_a',authority_multi_create_witness1=41}
 X4LAN_MULTI_CREATE_CLIENT=actual_client;X4LAN_RESOLVE_STRING=real_resolve or {}
 function ConvertStringToLuaID(v)return ffi.new('uint64_t',tonumber(v))end
 function ConvertIDTo64Bit(v)return v end
 function GetComponentData(_,...)
  local result={};for _,k in ipairs({...})do
   if k=='macro' then result[#result+1]='ship_gen_m_tugboat_01_a_macro'
   elseif k=='owner' then result[#result+1]='pioneers' else result[#result+1]=false end
  end;return unpack(result)
 end
 X4LAN_MULTI_CREATE_INSPECTOR={new_x4=function(cfg)
  assert(cfg.running and cfg.guard() and cfg.position_tolerance==2)
  return {arm_running=function()arms=arms+1;return true end,
   inspect=function(_,actor,sector,index,d)
    assert(cfg.guard() and arms==1 and actor=='0x29' and sector=='0x2b' and index==10055 and d.index==10055)
    return '41',true
   end}
 end}
 if use_real then
  X4LAN_MULTI_CREATE_INSPECTOR={new_x4=function(cfg)
   local obj=assert(real_inspector.new_x4(cfg));local arm=obj.arm_running
   obj.arm_running=function(self)arms=arms+1;return arm(self)end;return obj
  end}
 end
 function RegisterEvent(name,fn)assert(name=='X4AuthorityMultiCreateReceiver.Result' and not callback);callback=fn;return true end
 function GetCurRealTime()return now end
 function Unpause()ffi.C.TestUnpause()end
 function DebugError(s)logs[#logs+1]=s end
 function AddUITriggeredEvent(_,op,args)packets[#packets+1]={op=op,args=args};return true end
 dofile('tools/dev/authority_multi_create_running_run.lua')
 X4LAN_MULTI_CREATE_RUN_TICK();assert(#packets==0)
 if mode=='pause_lost' then ffi.C.TestPause();now=32;X4LAN_MULTI_CREATE_RUN_TICK();assert(logs[#logs]:match('ERROR'));return end
 X4LAN_MULTI_CREATE_RUN_TICK();assert(#packets==0)
 ffi.C.TestAdvance(1);X4LAN_MULTI_CREATE_RUN_TICK();assert(packets[1].op=='Initialize')
 local a=packets[1].args;callback(nil,a.request_id..'|Initialized|'..epoch)
 X4LAN_MULTI_CREATE_RUN_TICK();assert(arms==1 and packets[2].op=='Create')
 if mode=='foreign' then callback(nil,'bad|Created|10055|0x29');assert(logs[#logs]:match('ERROR'));return end
 callback(nil,packets[2].args.request_id..'|Created|10055|0x29');assert(packets[3].op=='Inspect')
 if mode~='no_progress' then ffi.C.TestAdvance(1) end
 callback(nil,packets[3].args.request_id..'|Inspected|10055|0x29|0x2b')
 if mode=='no_progress' then assert(logs[#logs]:match('ERROR'));return end
 assert(logs[#logs]:match('ROW create 10055 sector_a'))
 if mode=='pause_after_create' then ffi.C.TestPause();X4LAN_MULTI_CREATE_RUN_TICK();assert(logs[#logs]:match('ERROR'));return end
 now=2;ffi.C.TestAdvance(1);X4LAN_MULTI_CREATE_RUN_TICK();assert(logs[#logs]:match('DONE'))
 callback(nil,'late');assert(logs[#logs]:match('ERROR'))
end
for _,mode in ipairs({'success','pause_lost','foreign','pause_after_create'})do scenario(mode)end
if use_real then scenario('no_progress') end
