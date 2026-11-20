-- Disposable restart probe only. The expected marker is never configured here.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_recovery_probe~=true then return end
local ffi=require('ffi')
ffi.cdef[[bool IsStartmenu(void);bool IsPlayerValid(void);bool IsGamePaused(void);
bool IsSaveListLoadingComplete(void);void ReloadSaveList(void);
const char* GetSaveFolderPath(void);]]
local C=ffi.C
local state='initial';local failed=false;local pause_requested=false
local early_pause=cfg.authority_recovery_early_pause==true
local pause_observed=false
local function log(s) DebugError('[X4LAN] AUTH_RECOVERY '..s) end
local function profile()
 assert(cfg.test_profile=='45841' and type(cfg.authority_load_save_path)=='string')
 local p=C.GetSaveFolderPath();assert(p~=nil and p~=ffi.NULL)
 assert(ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_load_save_path)
end
local function hold_recovery_pause()
 if C.IsStartmenu() or not C.IsPlayerValid() then
  assert(not pause_observed,'recovered player lost before marker')
  return false
 end
 if not C.IsGamePaused() then
  assert(not pause_observed,'recovered world lost pause before marker')
  if not pause_requested then pause_requested=true;Pause() end
  return false
 end
 pause_observed=true
 return true
end
local function frame()
 if state=='done' then return end
 if state=='initial' then
  if C.IsStartmenu() then
   profile();C.ReloadSaveList();state='save_list';return
  end
  if not C.IsPlayerValid() then return end
  -- LoadGame can rebuild the UI on a playable frame. The host still
  -- requires this process's ordered REQUEST, matching marker and pause.
  profile();state='inspecting'
  if not early_pause then return end
 end
 if state=='save_list' then
  assert(C.IsStartmenu())
  if not C.IsSaveListLoadingComplete() then return end
  local entries=GetSaveList({save_008=true});assert(type(entries)=='table')
  local matches=0
  for _,entry in pairs(entries) do if entry.filename=='save_008' then matches=matches+1 end end
  assert(matches==1);state='loading';log('REQUEST');LoadGame('save_008');return
 end
 if state=='loading' and early_pause and not C.IsStartmenu() and C.IsPlayerValid() then
  profile();state='inspecting'
 end
 if state=='inspecting' then
  if early_pause then
   if not hold_recovery_pause() then return end
  elseif C.IsStartmenu() or not C.IsPlayerValid() then return end
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
  state='pausing'
 end
 if state=='pausing' then
  if not hold_recovery_pause() then return end
  state='done';log('PAUSED')
 end
end
SetScript('onUpdate',function()
 if failed then return end
 local ok=pcall(frame)
 if not ok then failed=true;log('ERROR') end
end)
