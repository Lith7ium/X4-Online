-- Synthetic event owner and fake-X4 adapter; no native process.
local mode=arg[1];local M=assert(loadfile('tools/dev/authority_sector_create_owner.lua'))()
if mode=='disabled' then assert(M.new_x4({enabled=false})==nil);return end
local events={};local paused=true;local player=true;local game=3;local path='/private/45841/save'
local current=0;local driver_state='new';local registration=0;local macro_calls=0
package.loaded.ffi={NULL={},typeof=function()return true end,cdef=function()end,string=function(s)return s end,C={
 GetSaveFolderPath=function()return path end,IsPlayerValid=function()return player end,IsGamePaused=function()return paused end,
 GetCurrentGameTime=function()return game end,
 IsValidComponent=function(v)return not(mode=='invalid_actor' and v==41) and not(mode=='invalid_candidate' and v==50) end,
 IsComponentOperational=function()return true end,IsComponentClass=function(_,c)return c=='ship' or c=='sector' end,
 GetContextByClass=function()return mode=='wrong_sector' and 99 or 43 end,
 GetObjectPositionInSector=function()
  if mode=='pause_during_pose' then paused=false end
  if mode=='time_during_pose' then game=game+1 end
  return {x=mode=='nan' and 0/0 or -400,y=100000,z=500}
 end}}
X4LAN_RESOLVE_STRING={actor_u64=function(v)if type(v)=='number' and v>=1 and v<=9007199254740991 and v%1==0 then return v end end,parse_hex=function(v)if v=='0x29' then return 41 elseif v=='0x2b' then return 43 end end}
X4LAN_AUTHORITY_SHIP_ENGINE={new=function()return {
 fleet_count=function()current=current+1;if mode=='fleet_duplicate' or (mode=='fleet_changed' and current>=2) then return 2 end;return 1 end,
 fleet=function()if mode=='fleet_duplicate' then return {50,50},false end;return {50},mode=='fleet_cut' end} end}
function GetCurRealTime()return 1 end
function ConvertStringToLuaID(v)return tonumber(v) end
function ConvertIDTo64Bit(v)return mode=='conversion' and v+1 or v end
function GetComponentData()macro_calls=macro_calls+1;if mode=='bad_macro' then return nil end;return 'ship_arg_s_fighter_01_a_macro' end
function RegisterEvent(name,fn)
 registration=registration+1
 if mode=='registration' and registration==3 then error('failed registration') end
 if mode=='registration_false' and registration==3 then return false end
 if mode=='registration_callback' and registration==3 then fn(nil,0) end
 assert(not events[name]);events[name]=fn
end
function AddUITriggeredEvent()return true end
local module={new=function(o)
 return {start=function()
  local valid,t=o.guard();assert(valid and t==3)
  assert(o.count()==1)
  local s=o.snapshot('0x29','0x2b');assert(s.actor_key=='41' and s.sector_key=='43' and s.x==-400)
  driver_state='active';return true
 end,tick=function()return true end,state=function()return driver_state end,
 event=function(_,name)
  if driver_state=='done' then driver_state='failed';return false end
  if name=='X4AuthorityShipCreateReceiver.Created' then driver_state='done';return true end
  return false
 end}
end}
if mode=='bad_path' then path='/wrong/45841/save' elseif mode=='unpaused' then paused=false end
local owner=assert(M.new_x4({enabled=true,exclusive_events=true,expected_save_path='/private/45841/save',epoch=string.rep('a',32),nonce=string.rep('b',32),macros={'sector_a','sector_b'},driver_module=module,report=function()return true end}))
local result=owner:start()
if mode=='ok' or mode=='late_event' then
 assert(result and owner:state()=='active' and owner:update()==false)
 events['X4AuthorityShipCreateReceiver.Created'](nil,3)
 assert(owner:state()=='pending_fence')
 local completed,why=owner:update();assert(completed==false and why=='pending_fence')
 if mode=='late_event' then events['X4AuthorityShipCreateReceiver.Created'](nil,3);assert(owner:state()=='failed') end
else
 assert(not result and owner:state()=='failed')
 -- A consistent size reaches the duplicate-key check only after the first
 -- candidate has passed conversion and macro lookup.
 if mode=='fleet_duplicate' then assert(current>=2 and macro_calls==1) end
end
print('sector-create owner synthetic '..mode..' passed')
