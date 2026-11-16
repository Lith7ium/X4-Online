-- Select only the bundled local UDP module for the current LuaJIT OS.
-- Importing this module does not load native code or open a socket.
local M={}
local paths={Linux='./extensions/x4_lan_lab/native/x4lan_net.so',
 Windows='./extensions/x4_lan_lab/native/x4lan_net_64.dll'}
function M.load(os_name,loadlib)
 local path=paths[os_name]
 assert(path and type(loadlib)=='function','unsupported local UDP module platform')
 local open,err=loadlib(path,'luaopen_x4lan_net')
 assert(type(open)=='function',err or 'local UDP module unavailable')
 local module=open()
 assert(type(module)=='table' and type(module.open)=='function' and type(module.monotonic)=='function',
  'invalid local UDP module')
 return module
end
return M
