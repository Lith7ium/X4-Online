local ffi=require('ffi')
ffi.cdef[[void TestMode(int);]]
local resolve=assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
local module=assert(loadfile('src/authority/lua/x4_multi_create_inspector.lua'))()
local function decimal(s)
 local n=ffi.new('uint64_t',0);local ten=ffi.new('uint64_t',10)
 for i=1,#s do n=n*ten+ffi.new('uint64_t',tonumber(s:sub(i,i))) end
 return n
end
function ConvertStringToLuaID(v)return decimal(v) end
function ConvertIDTo64Bit(v)return v end
local now=0
function GetCurRealTime()now=now+.001;return now end
function GetComponentData(ref,...)
 assert(ref==ffi.new('uint64_t',-1));local out={}
 for _,field in ipairs({...}) do
  if field=='macro' then out[#out+1]='ship_test_macro'
  elseif field=='owner' then out[#out+1]='argon'
  elseif field=='isdocked' or field=='isdocking' or field=='isinternallystored' then out[#out+1]=false
  else error('unexpected property') end
 end
 return unpack(out)
end
local d={index=10055,macro='ship_test_macro',owner='argon',sector='sector_a',x=1.25,y=-2.5,z=3.75}
local function make(overrides)
 local cfg={enabled=true,md_inspected=true,frame_confirmed=true,expected_save_path='/private/45841/save',
  guard=function()return true end,timeout=2,position_tolerance=0,resolve=resolve}
 for k,v in pairs(overrides or {})do cfg[k]=v end
 return assert(module.new_x4(cfg))
end
-- A uint64 above 2^53 is preserved through hex parsing, native FFI calls,
-- decimal conversion and both directions of Lua-ID conversion.
ffi.C.TestMode(0)
do local app=make();local key,ok=app:inspect('0xffffffffffffffff','0x2a',10055,d)
 assert(ok and key=='18446744073709551615' and app:state()=='ready') end
for _,mode in ipairs({1,2,3,4,5,6,7}) do
 ffi.C.TestMode(mode);local app=make();local _,ok=app:inspect('0xffffffffffffffff','0x2a',10055,d)
 assert(ok==false and app:state()=='failed',mode)
end
ffi.C.TestMode(0)
do local app=make();local _,ok=app:inspect('0x10000000000000000','0x2a',10055,d);assert(ok==false and app:state()=='failed') end
do local app=make();local _,ok=app:inspect('0xffffffffffffffff','0x0',10055,d);assert(ok==false and app:state()=='failed') end
do local app=make();local wrong={index=10055,macro='other',owner='argon',sector='sector_a',x=1.25,y=-2.5,z=3.75}
 local _,ok=app:inspect('0xffffffffffffffff','0x2a',10055,wrong);assert(ok==false and app:state()=='failed') end
do local app=make();local _,ok=app:inspect('0xffffffffffffffff','0x2a',10056,d);assert(ok==false and app:state()=='failed') end
do local app=make({guard=function()return false end});local _,ok=app:inspect('0xffffffffffffffff','0x2a',10055,d);assert(ok==false and app:state()=='failed') end
do
 local old=ConvertStringToLuaID
 ConvertStringToLuaID=function()return 9007199254740992 end
 local app=make();local _,ok=app:inspect('0xffffffffffffffff','0x2a',10055,d)
 assert(ok==false and app:state()=='failed');ConvertStringToLuaID=old
end
do
 local copy={index=10055,macro='ship_test_macro',owner='argon',sector='sector_a',x=1.25,y=-2.5,z=3.75}
 local app=make({guard=function()copy.owner='different';return true end})
 local _,ok=app:inspect('0xffffffffffffffff','0x2a',10055,copy);assert(ok==false and app:state()=='failed')
end
do
 local app
 app=make({guard=function()app:inspect('0xffffffffffffffff','0x2a',10055,d);return true end})
 local _,ok=app:inspect('0xffffffffffffffff','0x2a',10055,d);assert(ok==false and app:state()=='failed')
end
do
 local app=make();local wrong={index=10055,macro='ship_test_macro',owner='different',sector='sector_a',x=1.25,y=-2.5,z=3.75}
 local _,ok=app:inspect('0xffffffffffffffff','0x2a',10055,wrong);assert(ok==false and app:state()=='failed')
end
do
 local old=GetCurRealTime;GetCurRealTime=function()now=now+10;return now end
 local app=make();local _,ok=app:inspect('0xffffffffffffffff','0x2a',10055,d)
 assert(ok==false and app:state()=='failed');GetCurRealTime=old
end
do local ok=pcall(make,{md_inspected=false});assert(not ok) end
do local ok=pcall(make,{frame_confirmed=false});assert(not ok) end
-- The input options are frozen before any external callback can change them.
do
 local o={enabled=true,md_inspected=true,frame_confirmed=true,timeout=2,position_tolerance=0,
  clock=function()return 1 end,parse=function(s)return s end,key=function()return '1' end,
  reference=function()return 'local' end,same=function()return true end,live=function()return true end,
  properties=function()return 'ship_test_macro','argon',false,false,false end,
  position=function()return 100,-2.5,3.75 end}
 o.guard=function()o.position_tolerance=math.huge;o.position=function()return 1.25,-2.5,3.75 end;return true,100 end
 local app=assert(module.new(o));local _,ok=app:inspect('actor','sector',10055,d)
 assert(ok==false and app:state()=='failed')
end
do
 ffi.C.TestMode(0)
 local cfg={enabled=true,md_inspected=true,frame_confirmed=true,expected_save_path='/private/45841/save',
  timeout=2,position_tolerance=0,resolve=resolve}
 cfg.guard=function()cfg.expected_save_path='/unsafe/other/save';ffi.C.TestMode(7);return true end
 local app=assert(module.new_x4(cfg));local _,ok=app:inspect('0xffffffffffffffff','0x2a',10055,d)
 assert(ok==false and app:state()=='failed');ffi.C.TestMode(0)
end
assert(module.new_x4({enabled=false})==nil)
print('multi-create FFI fake ABI checks passed')
