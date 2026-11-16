-- Synthetic userdata/uint64 conversions; no native X4 process.
local mode=arg[1];local ffi=require('ffi');local big=9007199254740993ULL;local small=41ULL
local source=(mode=='number_good' or mode=='number_bad' or mode=='number_unsafe') and small or big
local opaque=newproxy();local diagnostics={};local got_macro=false
local fakeffi={NULL={},typeof=function()return true end,cdef=function()end,string=function(s)return s end,C={
 GetSaveFolderPath=function()return '/private/45841/save' end,IsPlayerValid=function()return true end,
 IsGamePaused=function()return true end,GetCurrentGameTime=function()return 3 end,
 IsValidComponent=function(v)return v==source end,IsComponentOperational=function()return true end,
 IsComponentClass=function(_,c)return c=='ship' end}}
package.loaded.ffi=fakeffi
X4LAN_RESOLVE_STRING={parse_hex=function()return nil end,actor_u64=function(v)
 if type(v)=='cdata' and ffi.istype('uint64_t',v) and v~=0 then return ffi.new('uint64_t',v) end
 if type(v)=='number' and v==v and v>=1 and v<=9007199254740991 and v%1==0 then return ffi.new('uint64_t',v) end
end}
X4LAN_AUTHORITY_SHIP_ENGINE={new=function()return {fleet_count=function()return 1 end,fleet=function()return {source},false end} end}
function GetCurRealTime()return 1 end
function RegisterEvent()end
function AddUITriggeredEvent()return true end
function ConvertStringToLuaID(s)
 if mode=='make_failure' then error('sensitive failure') end
 if mode=='nil_ref' then return nil end
 if mode=='unsupported' then return 'should not be logged' end
 if mode=='number_good' then return 41 end
 if mode=='number_bad' then return 42 end
 if mode=='number_unsafe' then return 9007199254740992 end
 if mode=='cdata_good' then return big end
 if mode=='cdata_bad' then return big+1ULL end
 return opaque
end
function ConvertIDTo64Bit(ref)
 if mode=='userdata_error' then error('sensitive roundtrip failure') end
 if mode=='userdata_bad' then return big+1ULL end
 if mode=='userdata_unsafe' then return 9007199254740992 end
 if ref==opaque then return big end
 return ref
end
function GetComponentData(ref,name)
 got_macro=true;assert(name=='macro')
 if mode:match('^userdata') then assert(ref==opaque) end
 return 'ship_arg_s_fighter_01_a_macro'
end
local module={new=function(o)return {start=function()assert(o.count()==1);return true end,state=function()return 'active' end,tick=function()return true end}end}
local owner=assert(assert(loadfile('tools/dev/authority_sector_create_owner.lua'))().new_x4({enabled=true,exclusive_events=true,
 expected_save_path='/private/45841/save',epoch=string.rep('a',32),nonce=string.rep('b',32),macros={'sector_a','sector_b'},driver_module=module,
 report=function()return true end,diagnostic=function(message)diagnostics[#diagnostics+1]=message end}))
local ok=owner:start()
local accepted=(mode=='userdata_good' or mode=='cdata_good' or mode=='number_good')
if accepted then assert(ok and got_macro and owner:state()=='active')
else
 assert(not ok and not got_macro and owner:state()=='failed')
 local expected={make_failure='count_conversion_make',nil_ref='count_conversion_null',unsupported='count_conversion_type_string',
  number_bad='count_conversion_input_number',number_unsafe='count_conversion_input_number',cdata_bad='count_conversion_input_cdata',
  userdata_error='count_conversion_roundtrip_call_userdata',userdata_bad='count_conversion_roundtrip_check_userdata',userdata_unsafe='count_conversion_roundtrip_check_userdata'}
 local text=table.concat(diagnostics,'|');assert(text:find('ADAPTER_FAIL '..expected[mode],1,true))
 assert(not text:find('9007199254740993',1,true) and not text:find('sensitive failure',1,true) and not text:find('should not be logged',1,true))
end
print('sector-create LuaID synthetic '..mode..' passed')
