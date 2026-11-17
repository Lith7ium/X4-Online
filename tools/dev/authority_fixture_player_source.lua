-- Private fixture player source. The participant owns the sole onUpdate hook.
local M = {}

function M.new(c)
 assert(type(c)=='table' and (type(c.net)=='table' or type(c.net)=='userdata') and type(c.net.send)=='function' and
  type(c.net.receive)=='function' and type(c.net.pending)=='function')
 assert(c.latest_cache==nil or type(c.latest_cache)=='boolean')
 assert(c.freeze_drain==nil or type(c.freeze_drain)=='boolean')
 assert(c.throttle==nil or type(c.throttle)=='table')
 assert(not c.freeze_drain or c.latest_cache==true)
 for _,name in ipairs({'seat_ready','paused','guard','make_session','fault'}) do
  assert(type(c[name])=='function',name)
 end
 local ready='READY|'..c.lease..'|'..c.attempt..'|'..c.epoch..'|'..c.generation
 local arm='ARM|'..c.lease..'|'..c.attempt..'|'..c.epoch..'|'..c.generation
 local state,session='waiting_seat',nil
 local was_paused=false
 local api={}
 local function fail(reason)
  if state~='failed' then state='failed';pcall(c.fault,reason) end
  return false
 end
 function api:tick()
  if state=='failed' then return false end
  local ok=pcall(function()
   assert(c.guard())
   if state=='waiting_seat' then
    if not c.seat_ready() then return end
    assert(c.net:send(ready));state='waiting_arm'
   elseif state=='waiting_arm' then
    local packet=c.net:receive()
    if packet==nil then return end
    assert(packet==arm and not c.paused() and c.guard())
    session=assert(c.make_session());assert(session:start());state='running'
   else
    assert(state=='running')
    if c.paused() then
     assert(session:quiescent() and c.net:pending()==false and c.guard())
     if c.latest_cache then was_paused=true end
    else
     if was_paused then
      if not c.freeze_drain then
       assert(c.net:pending()==false and session:after_resume() and c.net:pending()==false and c.guard())
      end
      was_paused=false
     end
     assert(session:tick() and c.guard())
    end
   end
   if c.throttle and state=='running' then assert(c.throttle:tick()) end
  end)
  if not ok then return fail('source_tick') end
  return true
 end
 function api:state() return state end
 return api
end

function M.new_x4(cfg)
 local ffi=require('ffi')
 ffi.cdef[[bool IsGamePaused(void); bool IsPlayerValid(void); const char* GetSaveFolderPath(void); double GetCurrentGameTime(void);]]
 local net=assert(X4LAN_LOCAL_UDP_MODULE.load(ffi.os,package.loadlib).open('127.0.0.1',cfg.port))
 local function guard()
  local path=ffi.C.GetSaveFolderPath()
  return ffi.C.IsPlayerValid() and path~=nil and path~=ffi.NULL and
   ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.save_path
 end
 local throttle
 if cfg.throttle_enabled then
  local throttle_net=assert(X4LAN_LOCAL_UDP_MODULE.load(ffi.os,package.loadlib).open('127.0.0.1',cfg.throttle_port))
  throttle=assert(X4LAN_FIXTURE_CLIENT_THROTTLE_DRIVER.new(cfg,throttle_net,guard,
   function() return ffi.C.IsGamePaused() end,function() return tonumber(ffi.C.GetCurrentGameTime()) end))
 end
 local owner
 owner=M.new{net=net,lease=cfg.lease,attempt=cfg.attempt,epoch=cfg.epoch,generation=cfg.generation,
  latest_cache=cfg.latest_cache,
  freeze_drain=cfg.freeze_drain,throttle=throttle,
  seat_ready=function() return X4LAN_FIXTURE_SEAT_READY==true end,
  paused=function() return ffi.C.IsGamePaused() end,guard=guard,
  fault=function(reason) DebugError('[X4LAN] AUTH_FIXTURE_PLAYER_SOURCE ERROR '..reason) end,
  make_session=function()
   return X4LAN_CLIENT_AUTHORITY_MOTION_SESSION.new_x4{enabled=true,fixture_slot=cfg.slot,
    epoch=cfg.epoch,generation=cfg.generation,index=cfg.slot+2,baseline=4,sector=cfg.sector,
    lease=cfg.lease,attempt=cfg.attempt,bootstrap_nonce=cfg.bootstrap_nonce,sampler_nonce=cfg.sampler_nonce,
    timeout=cfg.timeout,interval=cfg.interval,include_orientation=true,net=net,
    latest_cache=cfg.latest_cache,cache_module=X4LAN_FIXTURE_PLAYER_LATEST_CACHE,
    freeze_drain=cfg.freeze_drain,barrier_module=X4LAN_FIXTURE_PLAYER_FREEZE_BARRIER,
    reader=X4LAN_CLIENT_AUTHORITY_MOTION_READER,ipc=X4LAN_AUTHORITY_SOURCE_MOTION_IPC,
    bootstrap=X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP,sampler=X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER,
    descriptor=X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE,resolve=X4LAN_RESOLVE_STRING,
    expected_save_path=cfg.save_path,
    guard=function() return guard() and not ffi.C.IsGamePaused() end,
    grant=function(e,g,i) return e==cfg.epoch and g==cfg.generation and i==cfg.slot+2 and guard() end,
    fault=function(reason) DebugError('[X4LAN] AUTH_FIXTURE_PLAYER_SOURCE SESSION_ERROR '..reason) end}
  end}
 return owner
end

X4LAN_FIXTURE_PLAYER_SOURCE=M
return M
