-- Synthetic X4/MD doubles; no native process or real game state.
local real=require('ffi');local mode=arg[1];local arm=arg[2] or 'control';local events,queue,logs={},{},{}
local now,game,paused=1,3,true;local actor=real.new('uint64_t',41);local sector=real.new('uint64_t',42)
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local resumes,pauses,applies,releases,decisions=0,0,0,0,0
X4LAN_CONFIG={authority_npc_signal_ab=true,authority_sector_epoch=epoch,authority_npc_velocity_nonce=nonce,authority_npc_signal_mode=arm,authority_read_save_path='/private/save'}
package.loaded.ffi={NULL={},string=function(v)return v end,istype=real.istype,new=real.new,C={
 GetSaveFolderPath=function()return '/private/save' end,GetCurrentGameTime=function()return game end,
 IsGamePaused=function()return paused end,IsValidComponent=function(a)return a==actor end,
 IsComponentOperational=function()return true end,IsComponentClass=function()return true end,
 GetContextByClass=function()return sector end,GetObjectPositionInSector=function()return {x=game,y=2,z=3} end}}
function RegisterEvent(n,f)assert(not events[n]);events[n]=f end
function DebugError(s) logs[#logs+1]=s end
function GetCurRealTime()return now end
function Pause()assert(not paused);pauses=pauses+1;paused=true end
function Unpause()assert(paused);resumes=resumes+1;paused=false end
function X4LAN_SECTOR_READ_EXPORT()return actor,sector,'Patrol',3 end
assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
function AddUITriggeredEvent(screen,op,args)
 assert(screen=='X4AuthorityNPCSignalAB' and args.epoch==epoch)
 if mode=='dispatch' then return false end
 queue[#queue+1]={op=op,id=args.request_id,phase=args.phase}
end
assert(loadfile('tools/dev/authority_npc_signal_ab.lua'))()
local done=false
for _=1,1500 do
 now=now+0.1;if not paused then game=game+0.1 end
 local ok,result=pcall(X4LAN_NPC_SIGNAL_AB_READY);if not ok then break end
 if result then done=true;break end
 if #queue>0 and mode~='timeout' then
  local item=table.remove(queue,1);local op,id=item.op,item.id
  if mode=='wrong_id' then id=nonce..'-999' end
  if mode=='pause_loss' and op=='Sample' then paused=true end
  if mode=='actor_change' and op=='Apply' then actor=real.new('uint64_t',43) end
  if mode=='refuse' and op=='Apply' then events['X4AuthorityNPCSignalAB.Refused']();break end
  local event,row
  if op=='Begin' then event='Began';row=id..'|Patrol|started|0x29'
  elseif op=='Apply' then applies=applies+1;event='Applied';row=id..'|0x29'
  elseif op=='Release' then releases=releases+1;event='Released';row=id..'|0x29'
  elseif op=='Decision' then decisions=decisions+1;event='Decided';row=id..'|'..(mode=='wrong_mode' and 'wrong' or arm)..'|'..(arm=='control' and 'noop' or (mode=='order_persist' and 'skipped_order' or 'sent'))..'|'..(mode=='order_persist' and 'Other|started' or 'Patrol|started')..'|0x29'
  else
   event='Sampled';local order=((mode=='order_changed' and item.phase=='during') or (mode=='order_persist' and item.phase~='before')) and 'Other|started' or 'Patrol|started'
   row=id..'|'..item.phase..'|0x29|'..order
  end
  events['X4AuthorityNPCSignalAB.'..event](nil,row)
  if mode=='duplicate' then events['X4AuthorityNPCSignalAB.'..event](nil,row) end
 end
end
if mode=='ok' or mode=='order_changed' or mode=='order_persist' then
 assert(done and paused and resumes==1 and pauses==1 and applies==1 and releases==1 and decisions==1)
 assert(logs[#logs]:find('DONE mode='..arm..' before=3 during=3 after=5 tail=5',1,true))
else assert(not done and logs[#logs]:find('ERROR',1,true)) end
