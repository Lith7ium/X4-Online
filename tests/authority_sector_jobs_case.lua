-- Synthetic state-machine, events and FFI; no X4 or world writes.
local real=require('ffi');local mode=arg[1];local events,queue,logs={}, {}, {};local now,game=1,3;local paused=true
local high=real.new('uint64_t',9007199254740992)+real.new('uint64_t',1)
local actor=(mode=='highsame' or mode=='highmismatch') and high or 41
local resume_count,pause_count,begins,sample_count=0,0,0,0;local sector=42
local epoch=string.rep('a',32);local nonce=string.rep('b',32)
X4LAN_CONFIG={authority_sector_jobs_case=true,authority_jobs_mode=mode=='treatment' and 'treatment' or 'control',
 authority_sector_epoch=epoch,authority_jobs_nonce=nonce,authority_sector_slot=2,authority_read_save_path='/private/save',authority_jobs_min_game=5}
if mode=='disabled' then X4LAN_CONFIG.authority_sector_jobs_case=false end
package.loaded.ffi={NULL={},string=function(v) return v end,istype=real.istype,new=real.new,C={GetSaveFolderPath=function() return '/private/save' end,
 GetCurrentGameTime=function() return game end,IsGamePaused=function() return paused end,
 IsValidComponent=function(v) return v==actor end,IsComponentOperational=function() return true end,
 IsComponentClass=function() return true end,GetContextByClass=function() return sector end,
 GetObjectPositionInSector=function() return {x=game,y=0,z=0} end}}
function RegisterEvent(n,f) assert(not events[n]);events[n]=f end
function DebugError(s) logs[#logs+1]=s end
function GetCurRealTime() return now end
function Pause() assert(not paused);pause_count=pause_count+1;paused=true end
function Unpause() assert(paused);resume_count=resume_count+1;paused=false end
function X4LAN_SECTOR_READ_EXPORT() return actor,42,'Patrol',mode=='initial_game_mismatch' and 2 or 3 end
assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
function AddUITriggeredEvent(screen,op,a)
 assert(screen=='X4AuthoritySectorJobsCorrelated' and a.slot==2 and a.epoch==epoch)
 if op=='Begin' then begins=begins+1 else sample_count=sample_count+1 end
 if mode=='dispatch' then return false end
 queue[#queue+1]={op,a.request_id,a.mode}
end
assert(loadfile('tools/dev/authority_sector_jobs_case.lua'))()
if mode=='disabled' then assert(not next(events) and X4LAN_JOBS_CASE_READY==nil);return end
local done=false
for _=1,450 do
 now=now+0.1;if not paused then game=game+0.1 end
 local ok,res=pcall(X4LAN_JOBS_CASE_READY)
 if not ok then break end
 if res then done=true;break end
 if #queue>0 and mode~='timeout' and not (mode=='timeout_running' and queue[1][1]=='Sample') then
  local item=table.remove(queue,1);local op,id,case_mode=unpack(item)
  if mode=='wrong_id' or (mode=='wrong_id_sample' and op=='Sample') then id=nonce..'-999' end
  if mode=='sector_change' then sector=99 end
  if mode=='pause_loss' or (mode=='pause_loss_running' and op=='Sample') then paused=not paused end
  local callback=op=='Begin' and 'Began' or 'Sampled'
  local hex=((mode=='actor_mismatch' or (mode=='actor_mismatch_sample' and op=='Sample')) and '0x2a' or mode=='highsame' and '0x20000000000001' or
             mode=='highmismatch' and '0x20000000000002' or '0x29')
  local response=id..'|Patrol|'..hex..(op=='Sample' and '|started' or '')
  events['X4AuthoritySectorJobsCorrelated.'..callback](nil,response)
  if mode=='duplicate' then events['X4AuthoritySectorJobsCorrelated.'..callback](nil,response) end
 end
end
if mode=='control' or mode=='treatment' or mode=='highsame' then
 assert(done and paused and resume_count==1 and pause_count==1 and begins==1 and sample_count==6)
 assert(logs[#logs]:find('DONE mode='..(mode=='treatment' and 'treatment' or 'control')..' samples=6',1,true))
else assert(not done and logs[#logs]:find('ERROR',1,true)) end
if mode=='timeout_running' or mode=='actor_mismatch_sample' or mode=='pause_loss_running' or mode=='wrong_id_sample' then
 assert(resume_count==1 and pause_count==0 and begins==1)
end
print('jobs case synthetic '..mode..' passed')
