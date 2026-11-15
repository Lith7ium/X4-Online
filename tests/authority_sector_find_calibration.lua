-- Synthetic Lua and FFI only; no game process.
local real=require('ffi');local mode=arg[1];local events,queue,logs={},{},{}
local now,game,paused=1,3,true;local epoch,nonce=string.rep('a',32),string.rep('b',32)
X4LAN_CONFIG={authority_sector_find_calibration=mode~='disabled',authority_sector_epoch=epoch,authority_sector_find_nonce=nonce,authority_sector_find_macros={'sector_1','sector_2'},authority_read_save_path='/private/save'}
package.loaded.ffi={NULL={},string=function(v)return v end,istype=real.istype,new=real.new,C={
 GetSaveFolderPath=function()return '/private/save' end,GetCurrentGameTime=function()return game end,IsGamePaused=function()return paused end,
 IsValidComponent=function(a)return mode~='invalid' or tonumber(a)~=43 end,IsComponentOperational=function()return true end,
 IsComponentClass=function()return true end,GetContextByClass=function(a)return tonumber(a)==41 and real.new('uint64_t',43) or real.new('uint64_t',44) end}}
function RegisterEvent(n,f) assert(not events[n]);events[n]=f end
function DebugError(s) logs[#logs+1]=s end
function GetCurRealTime()return now end
function X4LAN_SECTOR_READ_EXPORT()return real.new('uint64_t',42),real.new('uint64_t',44),'none',3 end
function AddUITriggeredEvent(screen,op,a)
 assert(screen=='X4AuthoritySectorFindCalibration' and op=='Read' and a.epoch==epoch)
 if mode=='dispatch' then return false end
 queue[#queue+1]=a
end
assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
assert(loadfile('tools/dev/authority_sector_find_calibration.lua'))()
if mode=='disabled' then assert(not next(events) and X4LAN_SECTOR_FIND_CALIBRATION_READY==nil);return end
local done=false;local issued=0
for _=1,500 do
 now=now+.1
 local ok,res=pcall(X4LAN_SECTOR_FIND_CALIBRATION_READY);if not ok then break end
 if res then done=true;break end
 if #queue>0 and mode~='timeout' then
  local item=table.remove(queue,1);issued=issued+1
  if mode=='refused' then events['X4AuthoritySectorFindCalibration.Refused'](nil,'refused');break end
  if mode=='wrong_id' then item.request_id=nonce..'-999' end
  if mode=='wrong_epoch' then item.epoch=string.rep('c',32) end
  if mode=='wrong_macro' then item.macro='bad' end
  if mode=='pause_loss' then paused=false end
  local actor=item.slot==1 and '0x29' or '0x2a';local sector=item.slot==1 and '0x2b' or '0x2c'
  local found=mode=='wrong_find' and '0x2c' or sector
  local response=item.request_id..'|'..item.epoch..'|'..item.slot..'|'..actor..'|'..sector..'|'..found..'|'..item.macro
  events['X4AuthoritySectorFindCalibration.Result'](nil,response)
  if mode=='duplicate' then events['X4AuthoritySectorFindCalibration.Result'](nil,response) end
 end
end
if mode=='ok' then assert(done and paused and issued==2 and #logs==3 and logs[#logs]:find('DONE samples=2',1,true))
else assert(not done and logs[#logs]:find('ERROR',1,true)) end
print('sector-find synthetic '..mode..' passed')
