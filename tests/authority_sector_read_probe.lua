-- Synthetic MD callbacks and fake X4 calls; no process or game started.
local real=require('ffi');local mode=arg[1];local events={};local queue={};local logs={};local paused=true;local now=1;local conversions=0
local high=real.new('uint64_t',9007199254740992)+real.new('uint64_t',1)
local epoch=string.rep('a',32);local slot=mode=='slot2' and 2 or 1
X4LAN_CONFIG={authority_sector_read=true,authority_sector_epoch=epoch,authority_sector_slot=slot,authority_read_save_path='/private/save'}
if mode=='disabled' then X4LAN_CONFIG.authority_sector_read=false end
package.loaded.ffi={C={IsGamePaused=function() return paused end,GetSaveFolderPath=function() return '/private/save' end,
 IsValidComponent=function() return true end,IsComponentOperational=function() return true end,IsComponentClass=function() return true end,
 GetContextByClass=function() return real.new('uint64_t',10) end,GetCurrentGameTime=function() return 100 end,
 GetObjectPositionInSector=function() return {x=1,y=2,z=3} end},NULL={},cdef=function() end,typeof=function() return true end,
 string=function(v) return v end,istype=real.istype,new=real.new}
function RegisterEvent(n,f) assert(not events[n]);events[n]=f end
function AddUITriggeredEvent(s,o,a) if mode=='dispatch' then return false end;queue[#queue+1]={s,o,a} end
function ConvertIDTo64Bit(v) conversions=conversions+1;if mode=='unsafe' then return 9007199254740992 end
 if mode=='rounded' and type(v)=='cdata' and v==high then return high+real.new('uint64_t',1) end
 return real.new('uint64_t',v) end
function GetCurRealTime() return now end
function DebugError(s) logs[#logs+1]=s end
assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
assert(loadfile('tools/dev/authority_sector_read_probe.lua'))()
if mode=='disabled' then assert(not next(events) and #queue==0 and X4LAN_SECTOR_READ_READY==nil);return end
local function emit(n,v) assert(events[n]);events[n](nil,v) end
if mode=='dispatch' then assert(not pcall(X4LAN_SECTOR_READ_READY));return end
assert(not X4LAN_SECTOR_READ_STARTED());assert(not X4LAN_SECTOR_READ_READY());assert(X4LAN_SECTOR_READ_STARTED())
if mode=='clock' then now=0;assert(not pcall(X4LAN_SECTOR_READ_READY));return end
if mode=='late' then now=32;assert(not pcall(events['X4AuthoritySectorReferenceFixture.Verified'],nil,epoch));assert(#queue==1);return end
local n=0
while #queue>0 do
 local item=table.remove(queue,1);local screen,op,a=unpack(item);n=n+1
 assert(a.epoch==epoch)
 if mode=='pause' then paused=false;assert(not pcall(emit,screen..'.Verified',epoch));break end
 if op=='Verify' then emit(screen..'.Verified',epoch)
 elseif op=='Read' then
  assert(a.slot==slot);local prefix=screen..'.'
  if mode=='reorder' then emit(prefix..'OrderId','Patrol');break end
  emit(prefix..'Pilot','present');emit(prefix..'OrderId','Patrol');emit(prefix..'OrderState','started')
  local actor=42
  if mode=='changed' and n==3 then actor=43 end
  if mode=='highsame' or mode=='highchanged' or mode=='rounded' then actor=high end
  if mode=='highchanged' and n==3 then actor=high+real.new('uint64_t',1) end
  if mode=='unsafe-input' then actor=9007199254740992 end
  emit(prefix..'Actor',actor)
  if mode=='unsafe' or mode=='unsafe-input' or mode=='rounded' then break end
  emit(prefix..'Sector',10);emit(prefix..'Verified',epoch)
 else error('unexpected operation') end
end
if mode=='slot1' or mode=='slot2' or mode=='highsame' then
 assert(n==3 and X4LAN_SECTOR_READ_READY());assert(logs[#logs]:find('DONE slot='..slot,1,true))
else assert(not pcall(X4LAN_SECTOR_READ_READY)) end
if mode=='unsafe-input' then assert(conversions==0) end
if mode=='reorder' or mode=='unsafe' then
 local before=#queue;emit('X4AuthoritySectorReadGuard.Verified',epoch);assert(#queue==before)
end
print('sector read synthetic '..mode..' passed')
