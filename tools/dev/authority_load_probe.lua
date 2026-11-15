-- Explicit disposable-profile checkpoint-load diagnostic. No normal profile or save.
-- Lua is rebuilt by LoadGame, so the supervisor enforces the cross-reload order.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_load_probe~=true then return end
local ffi=require('ffi');local C=ffi.C
ffi.cdef[[bool IsStartmenu(void);bool IsPlayerValid(void);bool IsGamePaused(void);
bool IsSaveListLoadingComplete(void);void ReloadSaveList(void);
const char* GetSaveFolderPath(void);double GetCurrentGameTime(void);]]
local state='initial';local first_time;local failed=false
local function log(s) DebugError('[X4LAN] AUTH_LOAD '..s) end
local function check_profile()
 assert(cfg.test_profile=='45841' and type(cfg.authority_load_save_path)=='string')
 local p=C.GetSaveFolderPath();assert(p~=nil and p~=ffi.NULL)
 local actual=ffi.string(p):gsub('\\','/'):gsub('/+$','')
 assert(actual==cfg.authority_load_save_path,'unexpected save folder')
end
local function clock()
 local t=tonumber(C.GetCurrentGameTime())
 assert(t and t==t and t>=0 and t~=math.huge,'invalid game time')
 return t
end
local function frame()
 if failed or state=='done' then return end
 if state=='initial' then
  if C.IsStartmenu() then
   check_profile();C.ReloadSaveList();state='save_list';log('ARMED');return
  end
  if not C.IsPlayerValid() then return end
  check_profile();first_time=clock();state='observing'
  log(('READY time=%.17g'):format(first_time))
  if C.IsGamePaused() then
   assert(type(Unpause)=='function','Unpause unavailable');Unpause()
  end
  return
 end
 if state=='save_list' then
  if not C.IsStartmenu() then error('unexpected departure from start menu') end
  if not C.IsSaveListLoadingComplete() then return end
  local entries=GetSaveList({save_009=true})
  assert(type(entries)=='table','save list unavailable')
  local matches=0
  for _,entry in pairs(entries) do if entry.filename=='save_009' then matches=matches+1 end end
  assert(matches==1,'expected one private save slot')
  state='requested';log('REQUEST');LoadGame('save_009');return
 end
 if state=='observing' then
  assert(not C.IsStartmenu() and C.IsPlayerValid(),'loaded player unavailable')
  local current=clock()
  assert(current>=first_time,'game time regressed')
  if current>first_time and not C.IsGamePaused() then
   state='done';log(('ADVANCED time=%.17g'):format(current))
  end
 end
end
SetScript('onUpdate',function()
 local ok=pcall(frame)
 if not ok and not failed then failed=true;log('ERROR') end
end)
