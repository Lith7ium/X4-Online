-- UI probe using the real native loopback transport and controller; X4 is doubled.
local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local port=tonumber(arg[1]);local source=arg[2];local lease=arg[3];local epoch=arg[4]
local native=assert(package.loadlib(arg[5],'luaopen_x4lan_net'))()
local marker_required=arg[6]=='marked' or arg[6]=='badmarker';local marker_pending=nil;local stored_marker=nil
local paused=false;local game=10;local now=0;local pending=false;local update,events=nil,{}
local engine={ready=function() return true end,is_paused=function() return paused end,
 game_time=function() return game end,real_time=function() return now end,
 pause=function() paused=true end,resume=function() paused=false;game=game+1 end,
 saving_possible=function() return true end,save=function(slot,title)
  assert(slot=='save_009')
  if marker_required then assert(stored_marker and not marker_pending) end
  local f=assert(io.popen('gzip -c > '..source,'w'))
  local markerxml=''
  if stored_marker then markerxml='<script><refs type="string"><ref id="42" string="'..
   (arg[6]=='badmarker' and string.rep('f',32) or stored_marker)..'"/></refs></script>'..
   '<md><script name="X4AuthorityCheckpointMarker"><cue name="MarkerState"><vars>'..
   '<value name="$marker" type="string" value="42"/><value name="$loaded" type="integer"/>'..
   '</vars></cue></script></md>' end
  f:write('<savegame><info><save name="'..title..'"/><game time="'..game..'"/></info>'..markerxml..'</savegame>');assert(f:close())
  pending=true
 end}
X4LAN_CONFIG={authority_world_bridge=true,test_profile='45841',authority_control_port=port,
 authority_control_lease=lease,authority_world_epoch=epoch,authority_marker_required=marker_required}
package.loaded.ffi={cdef=function() end,C={IsPlayerValid=function() return true end,
 IsSaveListLoadingComplete=function() return true end,ReloadSaveList=function() end}}
package.loadlib=function() return function() return native end end
GetCurRealTime=function() return now end;GetSaveList=function() return {} end
SetScript=function(_,f) update=f end;DebugError=function(s) error(s) end
RegisterEvent=function(name,f) events[name]=f end
AddUITriggeredEvent=function(screen,control,params)
 assert(screen=='X4AuthorityCheckpointMarker' and control=='Store' and not marker_pending)
 marker_pending=params.marker
end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function() return engine end,
 register_save_event=function(_,state,register) register('gameSaved',function(_,success) state:on_game_saved(success) end);return true end}
assert(loadfile('src/authority/lua/control_state.lua'))()
assert(loadfile('src/authority/lua/local_control_bridge.lua'))()
assert(loadfile('tools/dev/authority_world_bridge_probe.lua'))()
for _=1,3000 do
 if marker_pending then stored_marker=marker_pending;marker_pending=nil;events['X4AuthorityCheckpointMarker.Stored'](nil,stored_marker) end
 if pending then pending=false;assert(events.gameSaved);events.gameSaved(nil,true) end
 update();now=now+.02;ffi.C.usleep(2000)
end
