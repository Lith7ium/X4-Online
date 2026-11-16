-- Fake-X4 readiness probe, no game process or network.
local real=require('ffi');local mode=arg[1];local events,queue,logs={},{},{}
local now,game,paused=1,3,true;local exports,contexts,game_reads=0,0,0;local epoch,nonce=string.rep('a',32),string.rep('b',32)
X4LAN_CONFIG={authority_sector_pair_ready=mode~='disabled',authority_sector_epoch=epoch,authority_pair_nonce=nonce,
 authority_pair_role='server',authority_pair_macros={'sector_a','sector_b'},authority_read_save_path='/private/save',authority_pair_deadline=60}
package.loaded.ffi={NULL={},string=function(v)return v end,istype=real.istype,new=real.new,C={
 GetSaveFolderPath=function()return '/private/save' end,IsPlayerValid=function()return true end,
 IsGamePaused=function()return paused end,GetCurrentGameTime=function()
  game_reads=game_reads+1;if mode=='slow_last_guard' and game_reads==5 then now=now+11 end
  return game
 end,
 IsValidComponent=function()return mode~='invalid' end,IsComponentOperational=function()return true end,
 IsComponentClass=function()return true end,GetContextByClass=function(a)
  contexts=contexts+1;if mode=='slow_ffi' and contexts==3 then now=now+11 end
  return tonumber(a)==41 and real.new('uint64_t',43) or real.new('uint64_t',44)
 end}}
function RegisterEvent(n,f)assert(not events[n]);events[n]=f end
function DebugError(s)logs[#logs+1]=s end
function GetCurRealTime()return now end
function X4LAN_SECTOR_READ_EXPORT()
 exports=exports+1;if mode=='slow_export' and exports==2 then now=now+11 end
 return real.new('uint64_t',42),real.new('uint64_t',44),'none',3
end
function AddUITriggeredEvent(screen,op,args)
 assert(screen=='X4AuthoritySectorPairReady' and op=='Read');queue[#queue+1]=args
 if mode=='slow_dispatch' then now=now+11 end
 return mode~='dispatch'
end
assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
assert(loadfile('tools/dev/authority_sector_pair_ready.lua'))()
if mode=='disabled' then assert(not next(events) and X4LAN_SECTOR_PAIR_TICK==nil);return end
local ready=false
for _=1,200 do
 now=now+.1;local ok,v=pcall(X4LAN_SECTOR_PAIR_TICK);if not ok then break end
 if v then
  ready=true
  if mode=='after_pause' then paused=false;pcall(X4LAN_SECTOR_PAIR_TICK);ready=false end
  if mode=='duplicate' then events['X4AuthoritySectorPairReady.Result'](nil,'bad');ready=false end
  break
 end
 if #queue>0 and mode~='timeout' then
  local q=table.remove(queue,1)
  if mode=='refused' then events['X4AuthoritySectorPairReady.Refused']();break end
  if mode=='wrong_id' then q.request_id=string.rep('c',32) end
  if mode=='wrong_epoch' then q.epoch=string.rep('c',32) end
  if mode=='pause_loss' then paused=false end
  local m1=mode=='wrong_macro' and 'bad' or 'sector_a'
  local actor2=mode=='wrong_actor' and '0x29' or '0x2a'
  events['X4AuthoritySectorPairReady.Result'](nil,q.request_id..'|'..q.epoch..'|0x29|0x2b|'..actor2..'|0x2c|'..m1..'|sector_b')
 end
end
if mode=='ok' then assert(ready and logs[#logs]:find('READY role=server',1,true))
else assert(not ready and logs[#logs]:find('ERROR',1,true)) end
print('pair readiness synthetic '..mode..' passed')
