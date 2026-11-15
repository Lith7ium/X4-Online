-- Synthetic Lua doubles: no game process or filesystem writes.
local real=require('ffi');local mode=arg[1];local events,queue,logs={},{},{}
local now,game,paused=1,5,true
local epoch,nonce=string.rep('a',32),string.rep('b',32)
X4LAN_CONFIG={authority_census_runtime_read=true,authority_census_epoch=epoch,authority_census_nonce=nonce,
 authority_census_limit=105,authority_census_deadline=60,authority_census_save_path='/private/save'}
package.loaded.ffi={NULL={},string=function(v)return v end,istype=real.istype,new=real.new,
 typeof=function()return true end,cdef=function()end,C={
 GetSaveFolderPath=function() return '/private/save' end,GetCurrentGameTime=function() return game end,
 IsGamePaused=function() return paused end,IsValidComponent=function(a) return tonumber(a)~=4 end,
 IsComponentOperational=function() return true end,IsComponentClass=function() return true end,
 GetContextByClass=function() return real.new('uint64_t',32) end,
 GetObjectPositionInSector=function(a) return {x=tonumber(a),y=2,z=3} end}}
function RegisterEvent(n,f) assert(not events[n]);events[n]=f end
function DebugError(s) logs[#logs+1]=s end
function GetCurRealTime() return now end
function AddUITriggeredEvent(screen,op,args)
 assert(screen=='X4AuthorityCensusRuntimeRead' and op=='Read' and args.epoch==epoch)
 queue[#queue+1]=args
end
assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
assert(loadfile('tools/dev/authority_census_runtime_read.lua'))()
local done=false
for _=1,300 do
 now=now+0.01
 local ok,result=pcall(X4LAN_CENSUS_RUNTIME_READY);if not ok then break end
 if result then done=true;break end
 if #queue>0 and mode~='timeout' then
  local item=table.remove(queue,1);local id=item.request_id
  if mode=='wrong_id' then id=nonce..'-999' end
  if mode=='pause_loss' then paused=false end
  local status,actor,sector='ok',string.format('0x%x',item.index+100),'0x20'
  if item.index==2 then status,actor,sector='unavailable','0','0' end
  if item.index==3 then status,actor,sector='no_sector','0','0' end
  if item.index==4 then actor='0x4' end
  if item.index==5 then status,actor,sector='docked_or_stored','0','0' end
  if mode=='duplicate' and item.index==6 then actor='0x65' end
  local row=id..'|'..epoch..'|'..item.index..'|'..status..'|'..actor..'|'..sector
  events['X4AuthorityCensusRuntimeRead.Result'](nil,row)
 end
 if mode=='timeout' then now=now+1 end
end
if mode=='ok' then
 assert(done and #logs==106 and logs[106]:find('DONE requested=105 ok=101 unavailable=1 no_sector=1 docked_or_stored=1 local_invalid=1 sectors=1',1,true))
else assert(not done and logs[#logs]:find('ERROR',1,true)) end
