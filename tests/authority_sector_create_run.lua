-- Fake-X4 orchestration test; never launches X4.
local mode=arg[1];local logs={};local now,game,paused=0,3,true;local state='new';local report
X4LAN_CONFIG={authority_sector_create_run=mode~='disabled',authority_read_save_path='/private/45841/save',
 authority_sector_create_deadline=90,authority_sector_epoch=string.rep('a',32),authority_sector_create_nonce=string.rep('b',32),authority_sector_create_macros={'sec1','sec2'}}
package.loaded.ffi={NULL={},string=function(v)return v end,C={GetSaveFolderPath=function()return '/private/45841/save' end,
 IsPlayerValid=function()return true end,IsGamePaused=function()return paused end,GetCurrentGameTime=function()return game end}}
function GetCurRealTime()return now end
function DebugError(s)logs[#logs+1]=s end
X4LAN_SECTOR_CREATE_DRIVER={}
X4LAN_SECTOR_CREATE_OWNER={new_x4=function(o)
 report=o.report
 return {start=function()state='running';return true end,update=function()
  if state=='running' then
   assert(report({index=3,stage='create',sector_macro='sec1',location='remote',x=-400,y=100000,z=500,count=5,game=game}))
   state='pending_fence'
  elseif mode=='late' then state='failed' end
  return false
 end,state=function()return state end}
end}
assert(loadfile('tools/dev/authority_sector_create_run.lua'))()
if mode=='disabled' then assert(X4LAN_SECTOR_CREATE_RUN_TICK==nil);return end
local done=false
for i=1,20 do
 now=now+.1
 if mode=='pause_loss' and i==3 then paused=false end
 if mode=='time_change' and i==3 then game=4 end
 if mode=='timeout' and i==3 then now=100 end
 local ok,value=pcall(X4LAN_SECTOR_CREATE_RUN_TICK)
 if not ok then break end
 if value then done=true;break end
end
if mode=='ok' then
 assert(done and logs[#logs]:find('DONE',1,true) and logs[#logs-1]:find('PENDING',1,true))
else assert(not done and logs[#logs]:find('ERROR',1,true)) end
print('sector create controller synthetic '..mode..' passed')
