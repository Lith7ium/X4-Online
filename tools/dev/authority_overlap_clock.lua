-- Installed only in the disposable overlap diagnostic. Read-only observer.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_overlap_clock~=true then return end
local ffi=require('ffi')
ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);double GetCurrentGameTime(void);]]
local C=ffi.C
local net,hello,failed=nil,0,false
local function update()
 if not X4LAN_AUTHORITY_RECOVERY_READY() then return end
 if not C.IsPlayerValid() then error('player unavailable') end
 if not net then
  local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
  net=lib.open('127.0.0.1',cfg.authority_overlap_clock_port)
 end
 local now=GetCurRealTime()
 if now>=hello then
  assert(net:send('CLOCK_READY|'..cfg.authority_control_lease));hello=now+.25
 end
 for _=1,8 do
  local packet=net:receive();if not packet then break end
  local nonce=packet:match('^CLOCK|([0-9a-f]+)$')
  assert(nonce and #nonce==32,'invalid clock request')
  local game=tonumber(C.GetCurrentGameTime())
  assert(game and game==game and game>=0 and game~=math.huge,'invalid clock')
  assert(net:send(('CLOCK_RESULT|%s|%s|%.17g'):format(nonce,C.IsGamePaused() and 'paused' or 'running',game)))
 end
end
function X4LAN_AUTHORITY_OVERLAP_CLOCK_UPDATE()
 if failed then return end
 local ok,err=pcall(update)
 if not ok then failed=true;DebugError('[X4LAN] AUTH_OVERLAP_CLOCK ERROR '..tostring(err)) end
end
