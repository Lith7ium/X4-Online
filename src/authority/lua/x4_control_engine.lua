-- Explicit factory only. No registration, save, pause, load or exit at load time.
-- The caller must independently establish exclusive control of this X4 process.
local M={}
function M.new(cfg)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 assert(cfg.test_profile=='45841','isolated test profile required')
 for _,name in ipairs({'Pause','Unpause','SaveGame','IsSavingPossible','GetCurRealTime'}) do
  assert(type(_G[name])=='function','required X4 UI function unavailable')
 end
 local ffi=require('ffi')
 ffi.cdef[[
 const char* GetSaveFolderPath(void);
 bool IsPlayerValid(void);
 bool IsGamePaused(void);
 double GetCurrentGameTime(void);
 ]]
 local C=ffi.C
 local raw=C.GetSaveFolderPath()
 assert(raw~=nil and raw~=ffi.NULL,'save folder unavailable')
 local path=ffi.string(raw):gsub('\\','/'):gsub('/+$','')
 assert(path:sub(-#'/45841/save')=='/45841/save','outside isolated profile')
 -- Capture the functions now. This is not protection against unrelated users
 -- or extensions invoking them; that requires an external admission fence.
 local pause,unpause,save,possible,realtime=Pause,Unpause,SaveGame,IsSavingPossible,GetCurRealTime
 return {
  ready=function() return C.IsPlayerValid() end,
  is_paused=function() return C.IsGamePaused() end,
  game_time=function() return tonumber(C.GetCurrentGameTime()) end,
  real_time=function() return realtime() end,
  pause=function() pause() end,
  resume=function() unpause() end,
  saving_possible=function() return possible(false) end,
  save=function(slot) save(slot,'X4 Authority isolated checkpoint') end,
 }
end
-- Explicit and single registration; the caller remains responsible for invoking
-- state:on_update() from its existing per-frame UI callback.
local registered=setmetatable({},{__mode='k'})
function M.register_save_event(cfg,state,register)
 if type(cfg)~='table' or cfg.enabled~=true then return false,'disabled' end
 assert(type(state)=='table' and type(state.on_game_saved)=='function' and type(register)=='function', 'missing event binding')
 assert(not registered[state],'save event already registered')
 -- Registration can have taken effect even if it then raises. Fence retries.
 registered[state]=true
 register('gameSaved',function(_,success) state:on_game_saved(success) end)
 return true
end
X4LAN_AUTHORITY_X4_CONTROL_ENGINE=M
return M
