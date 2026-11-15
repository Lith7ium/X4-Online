-- UI probe using the real native loopback transport and controller; X4 is doubled.
local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local port=tonumber(arg[1]);local source=arg[2];local lease=arg[3];local epoch=arg[4]
local native=assert(package.loadlib(arg[5],'luaopen_x4lan_net'))()
local paused=false;local game=10;local now=0;local pending=false;local update,events=nil,{}
local engine={ready=function() return true end,is_paused=function() return paused end,
 game_time=function() return game end,real_time=function() return now end,
 pause=function() paused=true end,resume=function() paused=false;game=game+1 end,
 saving_possible=function() return true end,save=function(slot,title)
  assert(slot=='save_009')
  local f=assert(io.popen('gzip -c > '..source,'w'))
  f:write('<savegame><info><save name="'..title..'"/><game time="'..game..'"/></info></savegame>');assert(f:close())
  pending=true
 end}
X4LAN_CONFIG={authority_world_bridge=true,test_profile='45841',authority_control_port=port,
 authority_control_lease=lease,authority_world_epoch=epoch}
package.loaded.ffi={cdef=function() end,C={IsPlayerValid=function() return true end,
 IsSaveListLoadingComplete=function() return true end,ReloadSaveList=function() end}}
package.loadlib=function() return function() return native end end
GetCurRealTime=function() return now end;GetSaveList=function() return {} end
SetScript=function(_,f) update=f end;DebugError=function(s) error(s) end
RegisterEvent=function(name,f) events[name]=f end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function() return engine end,
 register_save_event=function(_,state,register) register('gameSaved',function(_,success) state:on_game_saved(success) end);return true end}
assert(loadfile('src/authority/lua/control_state.lua'))()
assert(loadfile('src/authority/lua/local_control_bridge.lua'))()
assert(loadfile('tools/dev/authority_world_bridge_probe.lua'))()
for _=1,3000 do
 if pending then pending=false;assert(events.gameSaved);events.gameSaved(nil,true) end
 update();now=now+.02;ffi.C.usleep(2000)
end
