-- Actual control state, bridge and UI owner with simulated X4 and UDP.
local mode=assert(arg[1])
local incoming,sent,errors,events={},{},{},{}
local receive_count,race_packet,pending_failure=0,nil,false
local net={
 send=function(_,value)sent[#sent+1]=value;return true end,
 pending=function()
  if pending_failure then return nil end
  if race_packet~=nil then incoming[#incoming+1]=race_packet;race_packet=nil;return false end
  return #incoming>0
 end,
 receive=function()
  receive_count=receive_count+1
  local packet=table.remove(incoming,1)
  if packet=='' or (packet and #packet>768)then return nil end
  return packet
 end,
}
package.loaded.ffi={cdef=function()end,C={IsPlayerValid=function()return true end,
 IsSaveListLoadingComplete=function()return true end,ReloadSaveList=function()end}}
package.loadlib=function()return function()return {open=function()return net end}end end
local lease,epoch,marker=('a'):rep(32),('b'):rep(32),('c'):rep(32)
X4LAN_CONFIG={authority_world_bridge=true,test_profile='45841',authority_control_port=1234,
 authority_control_lease=lease,authority_world_epoch=epoch,authority_marker_required=true}
local now,paused,game,saves,pause_calls=0,false,10,0,0
local clock_failure=false
local engine={ready=function()return true end,is_paused=function()return paused end,
 game_time=function()return game end,real_time=function()if clock_failure then error('clock failed')end;return now end,
 pause=function()paused=true;pause_calls=pause_calls+1 end,resume=function()paused=false;game=game+1 end,
 saving_possible=function()return true end,save=function()saves=saves+1 end}
X4LAN_AUTHORITY_X4_CONTROL_ENGINE={new=function()return engine end,
 register_save_event=function(_,state,register)register('gameSaved',function(_,value)state:on_game_saved(value)end);return true end}
local marker_requested=nil
function AddUITriggeredEvent(_,_,args)marker_requested=args.marker end
function RegisterEvent(name,handler)events[name]=handler end
function GetCurRealTime()return now end
function GetSaveList()return {} end
local update
function SetScript(_,handler)update=handler end
function DebugError(message)errors[#errors+1]=message end
dofile('src/authority/lua/control_state.lua')
dofile('src/authority/lua/local_control_bridge.lua')
dofile('tools/dev/authority_world_bridge_probe.lua')
update();now=4;update()
assert(#errors==0 and #sent==1 and sent[1]:find('HELLO|',1,true))
local pause_command='CMD|'..lease..'|'..epoch..'|1|pause'
local function pause_and_confirm()
 incoming[1]=pause_command;update();now=now+.2;update()
 assert(pause_calls==1 and sent[#sent]:find('|pause|confirmed',1,true) and #errors==0)
end
if mode=='good' then
 pause_and_confirm();return
end
local bad=mode:find('empty',1,true) and '' or ('x'):rep(769)
if mode:find('marker_',1,true)==1 then
 pause_and_confirm()
 incoming[1]='CMD|'..lease..'|'..epoch..'|2|save|'..marker
 if mode:find('queued',1,true) then incoming[2]=bad end
 update()
 assert(marker_requested==marker and saves==0)
 if mode=='marker_callback_clock_error' then
  clock_failure=true
  assert(not pcall(events['X4AuthorityCheckpointMarker.Stored'],nil,marker))
  clock_failure=false
  assert(not pcall(events['X4AuthorityCheckpointMarker.Stored'],nil,marker))
  assert(saves==0)
  update();assert(#errors==1 and errors[1]:find('faulted',1,true))
  return
 end
 if mode:find('before_callback',1,true) then
  assert(#errors==0)
  if mode:find('pending_error',1,true) then pending_failure=true
  else incoming[1]=bad end
  local before,receipts_before=receive_count,#sent
  -- The marker callback arrives before another update. A waiting packet or
  -- a readiness error must prevent submission without consuming the packet.
  assert(not pcall(events['X4AuthorityCheckpointMarker.Stored'],nil,marker))
  assert(saves==0 and receive_count==before and #sent==receipts_before)
  if not pending_failure then assert(#incoming==1) end
  update()
  assert(#errors==1 and errors[1]:find('faulted',1,true) and saves==0)
  return
 end
 if not mode:find('queued',1,true)then assert(#errors==0);incoming[1]=bad;update()end
 assert(#errors==1 and errors[1]:find('receive',1,true) and saves==0)
 -- A separately registered event can still arrive after the update owner
 -- faults. It must not turn a failed transport into an actual save.
 assert(not pcall(events['X4AuthorityCheckpointMarker.Stored'],nil,marker))
 assert(saves==0);return
end
if mode=='pending_error' then pending_failure=true
elseif mode:find('race_',1,true)==1 then
 race_packet=bad;local before=receive_count;update()
 assert(receive_count==before and #incoming==1 and #errors==0)
else incoming[1]=bad;incoming[2]=pause_command end
update()
assert(#errors==1 and errors[1]:find('receive',1,true) and pause_calls==0 and saves==0)
local sent_before=#sent;update();assert(#sent==sent_before and pause_calls==0)
