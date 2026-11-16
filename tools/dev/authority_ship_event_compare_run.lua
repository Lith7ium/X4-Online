-- Private opt-in observer; the existing isolated load owner owns onUpdate.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_ship_event_compare_run~=true then return end
local ffi=require('ffi')
ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
local C=ffi.C
local phase,failed='initial',false
local app,start,last,game_last,resume_game,stop_at,drain_mark=nil,nil,nil,nil,nil,nil,nil
local rows=0
local function fail()
 if not failed then failed=true;DebugError('[X4LAN] AUTH_EVENT_COMPARE ERROR') end
 return false
end
local function clock()
 local t=GetCurRealTime()
 assert(type(t)=='number' and t==t and t>=0 and t<math.huge and (not last or t>=last))
 last=t;start=start or t;assert(t-start<=cfg.authority_ship_event_compare_window+60)
 return t
end
local function game()
 local t=tonumber(C.GetCurrentGameTime())
 assert(type(t)=='number' and t==t and t>=0 and t<math.huge and (not game_last or t>=game_last))
 game_last=t;return t
end
local function guard()
 local p=C.GetSaveFolderPath()
 if failed or p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=cfg.authority_load_save_path or not C.IsPlayerValid() then return false end
 local paused=C.IsGamePaused()
 if (phase=='initial' or phase=='attaching' or phase=='resume_request' or phase=='drain_wait' or phase=='draining' or phase=='done') and not paused then return false end
 if phase=='running' and paused then return false end
 game();return true
end
local function emit(s)DebugError('[X4LAN] AUTH_EVENT_COMPARE '..s)end
function X4LAN_EVENT_COMPARE_TICK()
 if failed then return end
 local ok=pcall(function()
  local t=clock();assert(guard())
  if phase=='initial' then
   local prior=game();phase='attaching'
   app=assert(X4LAN_SHIP_EVENT_COMPARE.new_x4({enabled=true,epoch=cfg.authority_ship_event_compare_epoch,
    generation=cfg.authority_ship_event_compare_generation,capacity=cfg.authority_ship_event_compare_capacity,
    timeout=10,resolve=X4LAN_RESOLVE_STRING,guard=guard,
    report=function(row)
     if failed or not guard() or row.sequence~=rows+1 then return false end
     rows=rows+1
     emit(('ROW %.0f %s %.0f %s'):format(row.sequence,row.kind,row.registry_index,row.actor_key));return true
    end,fault=fail}))
   assert(app:start());resume_game=prior;return
  end
  if phase=='attaching' then
   if app:state()=='idle' then emit('READY');phase='resume_request' else assert(app:tick()) end;return
  end
  if phase=='resume_request' then
   assert(C.IsGamePaused());Unpause();phase='resuming';return
  end
  if phase=='resuming' then
   assert(app:tick())
   if not C.IsGamePaused() and game()>resume_game then
    emit('RUNNING');stop_at=t+cfg.authority_ship_event_compare_window;phase='running'
   end
   return
  end
  if phase=='running' then
   assert(app:tick())
   if t>=stop_at then phase='pausing';Pause() end
   return
  end
  if phase=='pausing' then
   assert(app:tick());if C.IsGamePaused() then phase='drain_wait' end;return
  end
  if phase=='drain_wait' then
   local state,count=app:state();assert(type(count)=='number')
   if state=='idle' then drain_mark=count;assert(app:tick());phase='draining'
   else assert(app:tick()) end
   return
  end
  if phase=='draining' then
   local state,count=app:state()
   if state=='idle' and count>drain_mark then
    assert(game()>resume_game);emit(('DONE %.0f'):format(rows));phase='done';return
   end
   assert(app:tick());return
  end
  assert(phase=='done' and C.IsGamePaused())
 end)
 if not ok then fail() end
end
