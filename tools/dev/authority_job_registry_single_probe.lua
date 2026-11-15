-- Default-off, single owned X4 diagnostic. Loaded only into a disposable UI.
-- The existing world bridge calls X4LAN_JOB_REGISTRY_SINGLE_TICK in its own
-- update; this file must never install its own SetScript or start the game.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_job_single~=true then return end
local ffi=require('ffi');ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);]]
local C=ffi.C
local lease=assert(cfg.authority_job_lease);local epoch=assert(cfg.authority_job_epoch)
local phase='new';local net,app,hello_at=nil,nil,0
local function log(s) DebugError('[X4LAN] AUTH_JOB_SINGLE '..s) end
local function send(s)
 assert(net and net:send('JOB|'..lease..'|'..epoch..'|'..s)==true,'local job send failed')
end
local function fail()
 if phase=='failed' then return end
 phase='failed';log('ERROR')
 if net then pcall(send,'FAULT') end
end
local function report(row)
 if phase~='running' then return false end
 if row.epoch~=epoch or row.birth_confirmed~=false or row.delivery_confirmed~=false then return false end
 if row.classification~='previously_observed' and row.classification~='previously_unobserved_existing_index' and row.classification~='new_registry_entry' then return false end
 send(('EVENT|%.0f|%.0f|%s'):format(row.sequence,row.index,row.classification))
 return true
end
local function done(row)
 if phase~='running' or row.birth_confirmed~=false or row.delivery_confirmed~=false or row.coverage~='unknown' then return false end
 if row.classification~='inconclusive_no_events' and row.classification~='local_activations_observed' then return false end
 send(('DONE|%.0f|%.0f|%.0f|%s'):format(row.observed,row.acknowledged,row.baseline_count,row.classification))
 phase='done';log('DONE');return true
end
function X4LAN_JOB_REGISTRY_SINGLE_TICK()
 if phase=='failed' or not C.IsPlayerValid() then return end
 local ok=pcall(function()
  if not net then
   local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))()
   net=lib.open('127.0.0.1',cfg.authority_job_port)
  end
  local now=GetCurRealTime();assert(type(now)=='number' and now==now and now>=0 and now<math.huge)
  if phase=='new' and now>=hello_at then send('HELLO');hello_at=now+.25 end
  for _=1,4 do
   local packet=net:receive();if not packet then break end
   assert(packet=='JOBSTART|'..lease..'|'..epoch and phase=='new' and not C.IsGamePaused(),'unexpected job start')
   phase='running' -- before initialization: never retry an uncertain start
   send('STARTED') -- receipt of the start command, not initialization proof
   app=assert(X4LAN_AUTHORITY_JOB_REGISTRY_HOST.new_x4({enabled=true,epoch=epoch,baseline={},
    expected_save_path=cfg.authority_job_save_path,capacity=cfg.authority_job_capacity,
    window=cfg.authority_job_window,timeout=cfg.authority_job_timeout,
    probe=assert(X4LAN_AUTHORITY_JOB_REGISTRY_PROBE),report=report,done=done,fault=fail}))
   assert(app:start(),'job host initialization failed')
  end
  if phase=='running' and app then
   local alive,state=app:tick()
   assert(alive or state=='done','job host stopped')
  end
 end)
 if not ok then fail() end
end
