-- No X4. Exercise one-shot start, empty baseline, and event/summary framing.
local commands={};local output={};local now=1;local captured;local count=0
local lease,epoch=string.rep('a',32),string.rep('b',32)
X4LAN_CONFIG={authority_job_single=true,authority_job_lease=lease,authority_job_epoch=epoch,
 authority_job_port=1234,authority_job_save_path='/tmp/45841/save',authority_job_capacity=8,
 authority_job_window=2,authority_job_timeout=1}
package.loaded.ffi={cdef=function() end,C={IsPlayerValid=function()return true end,IsGamePaused=function()return false end}}
function GetCurRealTime() return now end
function DebugError(_) end
local net={send=function(_,v) output[#output+1]=v;return true end,
 receive=function() return table.remove(commands,1) end}
package.loadlib=function() return function() return {open=function() return net end} end end
X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={}
X4LAN_AUTHORITY_JOB_REGISTRY_HOST={new_x4=function(o)
 captured=o;assert(#o.baseline==0 and o.epoch==epoch)
 return {start=function() count=count+1;return true end,tick=function() return true,'waiting' end}
end}
assert(dofile('tools/dev/authority_job_registry_single_probe.lua')==nil)
X4LAN_JOB_REGISTRY_SINGLE_TICK()
assert(output[1]=='JOB|'..lease..'|'..epoch..'|HELLO')
commands[1]='JOBSTART|'..lease..'|'..epoch
X4LAN_JOB_REGISTRY_SINGLE_TICK()
assert(count==1 and output[2]=='JOB|'..lease..'|'..epoch..'|STARTED')
assert(captured.report({epoch=epoch,sequence=1,index=1,classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false}))
assert(output[3]=='JOB|'..lease..'|'..epoch..'|EVENT|1|1|new_registry_entry')
assert(captured.done({observed=1,acknowledged=1,baseline_count=0,classification='local_activations_observed',birth_confirmed=false,delivery_confirmed=false,coverage='unknown'}))
assert(output[4]=='JOB|'..lease..'|'..epoch..'|DONE|1|1|0|local_activations_observed')
commands[1]='JOBSTART|'..lease..'|'..epoch;X4LAN_JOB_REGISTRY_SINGLE_TICK()
assert(count==1 and output[#output]=='JOB|'..lease..'|'..epoch..'|FAULT')
print('single X4 job probe framing and one-shot checks passed')
