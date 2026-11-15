-- Synthetic only; fake engine, no game or world writes.
local real=require('ffi');local mode=arg[1];local events,queue,logs={},{},{}
local now,game,paused=1,3,true;local resumes,pauses=0,0
local epoch,nonce=string.rep('a',32),string.rep('b',32)
X4LAN_CONFIG={authority_sector_fingerprint=mode~='disabled',authority_sector_epoch=epoch,authority_fingerprint_nonce=nonce,authority_read_save_path='/private/save'}
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
function X4LAN_SECTOR_READ_EXPORT() return real.new('uint64_t',42),real.new('uint64_t',44),'Patrol',3 end
assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
function AddUITriggeredEvent(screen,op,a)
 assert(screen=='X4AuthoritySectorFingerprint' and op=='Read' and a.epoch==epoch)
 if mode=='dispatch' then return false end
 queue[#queue+1]=a
end
assert(loadfile('tools/dev/authority_sector_fingerprint.lua'))()
if mode=='disabled' then assert(not next(events) and X4LAN_SECTOR_FINGERPRINT_READY==nil);return end
local done=false;local issued=0
for _=1,500 do
 now=now+0.1;if not paused then game=game+0.1 end
 local ok,res=pcall(X4LAN_SECTOR_FINGERPRINT_READY);if not ok then break end
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
  if mode=='pause_loss' then paused=false end
  local attrs=item.slot==1 and 'LBT-457|ship_x|sector_x' or 'ABC-309|ship_y|sector_y'
  if mode=='missing_sector' then attrs=attrs:gsub('sector_x','null') end
  if mode=='changed_attributes' and issued==3 then attrs='ZZZ-999|ship_x|sector_x' end
  local response=item.request_id..'|'..item.epoch..'|'..item.slot..'|'..actor..'|'..sector..'|'..attrs
  events['X4AuthoritySectorFingerprint.Result'](nil,response)
  if mode=='duplicate' then events['X4AuthoritySectorFingerprint.Result'](nil,response) end
 end
end
if mode=='ok' then assert(done and paused and resumes==0 and pauses==0 and issued==4 and logs[#logs]:find('DONE samples=4',1,true))
else assert(not done and logs[#logs]:find('ERROR',1,true)) end
if mode=='missing_sector' then assert(logs[#logs]:find('ERROR sample_sector_macro shape_null',1,true)) end
if mode=='bad_hex' then assert(logs[#logs]:find('ERROR sample_row_format bytes_',1,true) and logs[#logs]:find('_separators_7',1,true)) end
if mode=='wrong_id' then assert(logs[#logs]:find('ERROR sample_request_id',1,true)) end
if mode=='pause_loss' then assert(logs[#logs]:find('ERROR sample_observe',1,true)) end
print('fingerprint synthetic '..mode..' passed')
