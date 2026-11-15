-- Disposable restart probe only. The expected marker is never configured here.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_recovery_probe~=true then return end
local ffi=require('ffi')
ffi.cdef[[bool IsStartmenu(void);bool IsPlayerValid(void);bool IsGamePaused(void);
bool IsSaveListLoadingComplete(void);void ReloadSaveList(void);
const char* GetSaveFolderPath(void);]]
local C=ffi.C
local state='initial';local failed=false;local pause_requested=false
local function log(s) DebugError('[X4LAN] AUTH_RECOVERY '..s) end
local function profile()
 assert(cfg.test_profile=='45841' and type(cfg.authority_load_save_path)=='string')
 local p=C.GetSaveFolderPath();assert(p~=nil and p~=ffi.NULL)
 assert(ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_load_save_path)
end
local function frame()
 if state=='done' then return end
 if state=='initial' then
  if C.IsStartmenu() then
   profile();C.ReloadSaveList();state='save_list';return
  end
  if not C.IsPlayerValid() then return end
  profile();state='inspecting';return
 end
 if state=='save_list' then
  assert(C.IsStartmenu())
  if not C.IsSaveListLoadingComplete() then return end
  local entries=GetSaveList({save_008=true});assert(type(entries)=='table')
  local matches=0
  for _,entry in pairs(entries) do if entry.filename=='save_008' then matches=matches+1 end end
  assert(matches==1);state='loading';log('REQUEST');LoadGame('save_008');return
 end
 if state=='inspecting' then
  if C.IsStartmenu() or not C.IsPlayerValid() then return end
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
  state='pausing'
 end
 if state=='pausing' then
  if C.IsStartmenu() or not C.IsPlayerValid() then return end
  if not C.IsGamePaused() then
   if not pause_requested then pause_requested=true;Pause() end
   return
  end
  state='done';log('PAUSED')
 end
end
SetScript('onUpdate',function()
 if failed then return end
 local ok=pcall(frame)
 if not ok then failed=true;log('ERROR') end
end)
