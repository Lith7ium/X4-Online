-- X4 UI adapter for client_load_barrier. Disabled by default; no registration.
local M={}
function M.new(cfg)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 local ffi=require('ffi')
 ffi.cdef[[bool IsStartmenu(void);bool IsPlayerValid(void);bool IsGamePaused(void);
 bool IsSaveListLoadingComplete(void);void ReloadSaveList(void);
 double GetCurrentGameTime(void);]]
 local C=ffi.C
 for _,name in ipairs({'GetSaveList','LoadGame','Pause'}) do assert(type(_G[name])=='function','missing '..name) end
 local get,load,pause=GetSaveList,LoadGame,Pause
 return {
  in_startmenu=function() return C.IsStartmenu() end,
  refresh=function() assert(C.IsStartmenu());C.ReloadSaveList() end,
  save_available=function(slot)
   if not C.IsStartmenu() or not C.IsSaveListLoadingComplete() then return false end
   local entries=get({[slot]=true});if type(entries)~='table' then return false end
   local count=0
   for _,v in pairs(entries) do if v.filename==slot then count=count+1 end end
   return count==1
  end,
  load=function(slot) load(slot) end,
  player_valid=function() return C.IsPlayerValid() end,
  is_paused=function() return C.IsGamePaused() end,
  game_time=function() return tonumber(C.GetCurrentGameTime()) end,
  pause=function() pause() end,
 }
end
X4LAN_AUTHORITY_X4_CLIENT_LOAD_ENGINE=M
return M
