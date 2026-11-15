-- Synthetic only; fake engine, no game or world writes.
local real=require('ffi');local mode=arg[1];local events,queue,logs={},{},{}
local now,game,paused=1,3,true;local resumes,pauses=0,0
local epoch,nonce=string.rep('a',32),string.rep('b',32)
X4LAN_CONFIG={authority_multi_sector_read=mode~='disabled',authority_sector_epoch=epoch,authority_multi_nonce=nonce,authority_read_save_path='/private/save'}
package.loaded.ffi={NULL={},string=function(v)return v end,istype=real.istype,new=real.new,C={
 GetSaveFolderPath=function() return '/private/save' end,GetCurrentGameTime=function() return game end,IsGamePaused=function() return paused end,
 IsValidComponent=function() return true end,IsComponentOperational=function() return true end,
 IsComponentClass=function() return true end,GetContextByClass=function(a) if a==real.new('uint64_t',41) then return real.new('uint64_t',43) else return real.new('uint64_t',44) end end,
 GetObjectPositionInSector=function(a) return {x=tonumber(a)+game,y=0,z=0} end}}
function RegisterEvent(n,f) assert(not events[n]);events[n]=f end
function DebugError(s) logs[#logs+1]=s end
function GetCurRealTime() return now end
function Pause() assert(not paused);pauses=pauses+1;paused=true end
function Unpause() assert(paused);resumes=resumes+1;paused=false end
function X4LAN_MULTI_SECTOR_INITIAL() return real.new('uint64_t',42),real.new('uint64_t',44),3 end
assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
function AddUITriggeredEvent(screen,op,a)
 assert(screen=='X4AuthorityMultiSectorRead' and op=='Read' and a.epoch==epoch)
 if mode=='dispatch' then return false end
 queue[#queue+1]=a
end
assert(loadfile('tools/dev/authority_multi_sector_read.lua'))()
if mode=='disabled' then assert(not next(events) and X4LAN_MULTI_SECTOR_READY==nil);return end
local done=false;local issued=0
for _=1,500 do
 now=now+0.1;if not paused then game=game+0.1 end
 local ok,res=pcall(X4LAN_MULTI_SECTOR_READY);if not ok then break end
 if res then done=true;break end
 if #queue>0 and mode~='timeout' then
  local item=table.remove(queue,1);issued=issued+1
  if mode=='wrong_id' then item.request_id=nonce..'-999' end
  if mode=='wrong_epoch' then item.epoch=string.rep('c',32) end
  local actor=item.slot==1 and '0x29' or '0x2a';local sector=item.slot==1 and '0x2b' or '0x2c'
  if mode=='actor_change' and issued==3 then actor='0x2a' end
  if mode=='sector_change' and issued==3 then sector='0x2c' end
  if mode=='initial_mismatch' and item.slot==2 then actor='0x29';sector='0x2b' end
  if mode=='bad_hex' then actor='29' end
  if mode=='pause_loss' then paused=true end
  local response=item.request_id..'|'..item.epoch..'|'..item.slot..'|'..actor..'|'..sector
  events['X4AuthorityMultiSectorRead.Result'](nil,response)
  if mode=='duplicate' then events['X4AuthorityMultiSectorRead.Result'](nil,response) end
 end
end
if mode=='ok' then assert(done and paused and resumes==1 and pauses==1 and issued==6 and logs[#logs]:find('DONE samples=6',1,true))
else assert(not done and logs[#logs]:find('ERROR',1,true)) end
print('multi-sector synthetic '..mode..' passed')
