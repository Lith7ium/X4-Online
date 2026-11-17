-- Loaded only in the disposable single-process fixture measurement.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_single_measure~=true then return end
local ffi=require('ffi')
ffi.cdef[[bool IsStartmenu(void);bool IsPlayerValid(void);bool IsGamePaused(void);
const char* GetSaveFolderPath(void);double GetCurrentGameTime(void);]]
local C=ffi.C
local net,owner
local function valid()
 if C.IsStartmenu() or not C.IsPlayerValid() or not X4LAN_AUTHORITY_MARKER_READY() then return false end
 local path=C.GetSaveFolderPath()
 return path~=nil and path~=ffi.NULL and cfg.test_profile=='45841' and
  ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_load_save_path
end
function X4LAN_FIXTURE_SINGLE_MEASURE_UPDATE()
 if not owner then
  local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
  net=lib.open('127.0.0.1',cfg.authority_single_measure_port)
  owner=X4LAN_FIXTURE_SINGLE_MEASURE.new({valid=valid,paused=function() return C.IsGamePaused() end,
   clock=function() return tonumber(C.GetCurrentGameTime()) end,
   unpause=function() assert(type(Unpause)=='function');Unpause() end,
   send=function(s) return net:send(s) end,receive=function() return net:receive() end,
   error=function(s) DebugError('[X4LAN] AUTH_SINGLE_MEASURE ERROR '..s) end},cfg.authority_single_measure_lease)
 end
 owner()
end
