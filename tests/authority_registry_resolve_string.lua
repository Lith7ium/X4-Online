-- Synthetic only; no game, network or game-state writes.
local ffi=require('ffi');local m=assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
assert(tostring(m.actor_u64(9007199254740991))=='9007199254740991ULL')
for _,value in ipairs({0, -1, 1.5, 9007199254740992, math.huge, 0/0}) do assert(m.actor_u64(value)==nil) end
assert(tostring(m.actor_u64(m.parse_hex('0xffffffffffffffff')))=='18446744073709551615ULL')
for _,text in ipairs({'','0','123','f','0x0','0x','g','0xg','1.0',' 1','1|2','0x10000000000000000','0x00000000000000000'}) do
 assert(m.parse_hex(text)==nil,'accepted '..text)
end
assert(tostring(m.parse_hex('0xffffffffffffffff'))=='18446744073709551615ULL')
assert(tostring(m.parse_hex('0X8000000000000001'))=='9223372036854775809ULL')
assert(tostring(m.parse_hex('0xf'))=='15ULL')
local epoch,id=string.rep('a',32),string.rep('b',32)
local function setup(expected)
 local t=0;local c=assert(m.new({enabled=true,epoch=epoch,timeout=2,
  issue=function() return true end,clock=function() return t end,
  expected_actor=function() return expected end,valid=function() return true end}))
 return c,function(v) t=v end
end
local row=id..'|'..epoch..'|1|ok|0xffffffffffffffff'
do
 local c=setup(m.parse_hex('0xffffffffffffffff'));assert(c:resolve(id,1));local ok,r=c:response(row)
 assert(ok and r.index==1 and r.request_id==id)
end
do
 local c=setup(m.parse_hex('0xffffffffffffffff'));assert(c:resolve(id,1));assert(c:response(row))
 assert(c:resolve(string.rep('c',32),1))
 local ok,why=c:response(row);assert(not ok and why=='mismatch' and c:state()=='failed')
end
for _,bad in ipairs({row..'f',row..'|extra',row:gsub('ffff','fffg',1),row:gsub('|1|','|2|'),row:gsub('^b','c')}) do
 local c=setup(m.parse_hex('0xffffffffffffffff'));assert(c:resolve(id,1));assert(not c:response(bad) and c:state()=='failed')
end
do
 local c=setup(ffi.new('uint64_t',42));assert(c:resolve(id,1));assert(not c:response(row) and c:state()=='failed')
end
do
 local c=setup(ffi.new('uint64_t',42));assert(c:resolve(id,1))
 local ok,why=c:response(id..'|'..epoch..'|1|unavailable|0');assert(not ok and why=='unavailable')
end
do
 local c,set=setup(m.parse_hex('0xffffffffffffffff'));assert(c:resolve(id,1));set(2)
 local ok,why=c:response(row);assert(not ok and why=='timeout')
end
print('ResolveString exact-uint64 synthetic checks passed')
