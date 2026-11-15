-- Synthetic event ownership/state transitions; no X4 or network.
local mode=arg[1];local paused=true;local now=0;local logs={};local callbacks={}
local epoch,run=string.rep('a',32),string.rep('b',32);local pending=false;local desc_ticks=0
local host_state='new';local opts;local emitted=false
X4LAN_CONFIG={authority_job_attach=mode~='disabled',authority_job_descriptor=true,
 authority_job_registry_epoch=epoch,authority_ticket={world_epoch=run},authority_load_save_path='/private/45841/save',authority_job_window=1}
package.loaded.ffi={NULL={},string=function(v)return v end,C={GetSaveFolderPath=function()return '/private/45841/save' end,
 IsPlayerValid=function()return true end,IsGamePaused=function()return paused end}}
function GetCurRealTime() return now end
function DebugError(s) logs[#logs+1]=s end
function RegisterEvent(name,cb) assert(not callbacks[name]);callbacks[name]=cb end
function Unpause() assert(paused);paused=false end
function Pause() assert(not paused);paused=true end
X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={}
X4LAN_AUTHORITY_JOB_REGISTRY_HOST={new_x4=function(o)
 opts=o;assert(o.expose_actor and o.exclusive_registry_consumer)
 return {start=function() assert(paused);host_state='attaching';return true end,
  state=function()return host_state end,
  tick=function()
   assert(not pending,'host tick while descriptor is outstanding')
   if host_state=='attaching' then host_state='attached_wait_running';return true,host_state end
   assert(not paused)
   if not emitted then
    emitted=true;host_state='front'
    assert(o.report({epoch=epoch,sequence=1,index=10055,classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false},'actor'))
    host_state='waiting';return true,host_state
   end
   host_state='done';assert(o.done({registry_mode='attached',baseline_count=10054,baseline_known_count=0,
    observed=1,acknowledged=1,classification='local_activations_observed',birth_confirmed=false,delivery_confirmed=false,coverage='unknown'}));return false,'done'
  end}
 end}
X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE={new_x4=function(o)
 assert(o.actor=='actor' and o.row.index==10055 and o.request_id==run and o.guard())
 pending=true
 return {start=function()return true end,
  tick=function() desc_ticks=desc_ticks+1;assert(o.guard());return mode~='timeout' end,
  abort=function() pending=false;return false end,
  close=function()pending=false;return true end,
  response=function(_,v)
   if v~='valid' then return false end
   assert(o.guard())
   return true,{epoch=epoch,sequence=1,index=10055,macro='ship_a',owner='argon',sector_macro='sector_a',
    x=1,y=2,z=3,game_before_request=10,game_before_pose=10,game_after_pose=11,
    descriptor_atomic=false,birth_confirmed=false,delivery_confirmed=false}
  end}
 end}
assert(loadfile('tools/dev/authority_job_descriptor_attach.lua'))()
if mode=='disabled' then assert(X4LAN_JOB_ATTACH_UPDATE==nil);return end
local done=false
for _=1,40 do
 now=now+.1
 local ok,result=pcall(X4LAN_JOB_ATTACH_UPDATE)
 if not ok then break end
 if result then done=true;break end
 if pending and desc_ticks>=1 then
  if mode=='ok' then callbacks['X4AuthorityJobDescriptorProbe.Result'](nil,'valid')
  elseif mode=='bad_response' then callbacks['X4AuthorityJobDescriptorProbe.Result'](nil,'bad')
  elseif mode=='queue_fault' then opts.fault('queue overflow') end
 end
end
if mode=='ok' then
 assert(done and paused and not pending)
 for _,word in ipairs({'READY','RESUMED','EVENT','SAMPLE','SUMMARY','PAUSED'}) do
  local found=false;for _,row in ipairs(logs) do if row:find(word,1,true) then found=true end end;assert(found,word)
 end
else assert(not done and logs[#logs]:find('ERROR',1,true)) end
print('job descriptor attach synthetic '..mode..' passed')
