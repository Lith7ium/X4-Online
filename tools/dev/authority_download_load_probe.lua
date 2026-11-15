-- Isolated supervisor-owned diagnostic; no multiplayer admission is emitted.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_download_load~=true then return end
local ffi=require('ffi');ffi.cdef[[const char* GetSaveFolderPath(void);]]
local function profile()
 assert(cfg.test_profile=='45841')
 local p=ffi.C.GetSaveFolderPath();assert(p~=nil and p~=ffi.NULL)
 assert(ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_load_save_path)
end
local t=cfg.authority_ticket
local fields={'world_epoch','connection_handle','baseline_id','load_generation','checkpoint_id','sha256','attempt_id','slot'}
local function emit(event,ticket)
 local values={event}
 for _,key in ipairs(fields) do values[#values+1]=tostring(ticket[key]) end
 DebugError('[X4LAN] AUTH_DOWNLOAD_LOAD '..table.concat(values,'|'))
end
local ok,engine=pcall(X4LAN_AUTHORITY_X4_CLIENT_LOAD_ENGINE.new,{enabled=true})
assert(ok and engine)
local barrier=X4LAN_AUTHORITY_CLIENT_LOAD_BARRIER.new({enabled=true,ticket=t},engine,emit)
local state='initial';local failed=false
local function frame()
 if state=='done' then return end
 if state=='initial' then
  if engine.in_startmenu() then
   profile();engine.refresh();state='waiting'
  elseif engine.player_valid() then
   profile();barrier.observe_pause();state='observing'
  end
 elseif state=='waiting' then
  assert(engine.in_startmenu())
  if engine.save_available(t.slot) then state='loading';barrier.begin() end
 elseif state=='observing' then
  if barrier.update() then state='done' end
 end
end
SetScript('onUpdate',function()
 if failed then return end
 local success=pcall(frame)
 if not success then failed=true;DebugError('[X4LAN] AUTH_DOWNLOAD_LOAD ERROR') end
end)
