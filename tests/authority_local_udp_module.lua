local module=dofile('src/authority/lua/local_udp_module.lua')
local called=0
local native={open=function()end,monotonic=function()end}
local function loader(expected)
 return function(path,symbol)
  called=called+1
  assert(path==expected and symbol=='luaopen_x4lan_net')
  return function()return native end
 end
end
assert(module.load('Linux',loader('./extensions/x4_lan_lab/native/x4lan_net.so'))==native)
assert(module.load('Windows',loader('./extensions/x4_lan_lab/native/x4lan_net_64.dll'))==native)
assert(called==2)
assert(not pcall(module.load,'OSX',loader('never')) and called==2)
assert(not pcall(module.load,'Windows',function()called=called+1;return nil,'missing' end) and called==3)
assert(not pcall(module.load,'Windows',function()return function()return {open=function()end}end end))
assert(not pcall(module.load,'Windows',function()return function()return nil end end))
