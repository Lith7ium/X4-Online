-- Synthetic engine and host only; no X4 process.
local mode=arg[1];local paused=true;local now=0;local logs={};local resumes,pauses=0,0
local epoch,run=string.rep('a',32),string.rep('b',32)
X4LAN_CONFIG={authority_job_attach=mode~='disabled',authority_job_registry_epoch=epoch,authority_ticket={world_epoch=run},authority_load_save_path='/private/45841/save',authority_job_window=1}
package.loaded.ffi={NULL={},string=function(v)return v end,C={GetSaveFolderPath=function()return mode=='bad_path' and '/other' or '/private/45841/save' end,IsPlayerValid=function()return true end,IsGamePaused=function()return paused end}}
function GetCurRealTime() return now end
function DebugError(s) logs[#logs+1]=s end
function Unpause() assert(paused and logs[#logs]:find('READY',1,true));paused=false;resumes=resumes+1 end
function Pause() assert(not paused);paused=true;pauses=pauses+1 end
X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={}
X4LAN_AUTHORITY_JOB_REGISTRY_HOST={new_x4=function(o)
 assert(o.epoch==epoch and o.attach_saved_registry and o.exclusive_registry_consumer and o.expected_last==10054 and #o.baseline==0)
 local state='new';local n=0
 return {start=function() assert(paused);state='attaching';return true end,
  state=function()return state end,
  tick=function()
   if state=='attaching' then
    if mode=='fault' then o.fault('fake');return false,'failed' end
    assert(paused);state='attached_wait_running';return true,state
   end
   assert(not paused);n=n+1
   if n==1 then
    assert(o.report({epoch=epoch,sequence=1,index=10055,classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false}))
    return true,'running'
   end
   state='done';assert(o.done({registry_mode='attached',baseline_count=10054,baseline_known_count=0,observed=1,acknowledged=1,classification='local_activations_observed',birth_confirmed=false,delivery_confirmed=false,coverage='unknown'}));return false,'done'
  end}
 end}
assert(loadfile('tools/dev/authority_job_attach.lua'))()
if mode=='disabled' then assert(X4LAN_JOB_ATTACH_UPDATE==nil);return end
local done=false
for _=1,50 do
 now=now+.1
 if mode=='pause_loss' and #logs==0 and now>.1 then paused=false end
 local ok,result=pcall(X4LAN_JOB_ATTACH_UPDATE)
 if not ok then break end
 if result then done=true;break end
end
if mode=='ok' then
 assert(done and paused and resumes==1 and pauses==1 and #logs==5)
 for i,word in ipairs({'READY','RESUMED','EVENT','SUMMARY','PAUSED'}) do assert(logs[i]:find(word,1,true)) end
else assert(not done and logs[#logs]:find('ERROR',1,true) and resumes==0) end
print('job attach synthetic '..mode..' passed')
