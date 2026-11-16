-- Private diagnostic only: the existing download-load script owns onUpdate.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_multi_create_run~=true then return end
local ffi=require('ffi')
ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
local C=ffi.C
local first_game=nil
local function guard()
 local p=C.GetSaveFolderPath()
 if p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=cfg.authority_load_save_path or
    not C.IsPlayerValid() or not C.IsGamePaused() then return false end
 local g=tonumber(C.GetCurrentGameTime())
 if not g or g~=g or g<0 or g==math.huge then return false end
 if not first_game then first_game=g end
 return first_game==g
end
local scenario;local failed=false
local function fail()
 if not failed then failed=true;DebugError('[X4LAN] AUTH_MULTI_CREATE ERROR') end
end
assert(RegisterEvent('X4AuthorityMultiCreateReceiver.Result',function(_,value)
 if failed or not scenario then fail();return end
 local ok,accepted=pcall(scenario.event,scenario,value)
 if not ok or accepted~=true then fail() end
end)~=false)
function X4LAN_MULTI_CREATE_RUN_TICK()
 if failed then return end
 local ok=pcall(function()
  if not scenario then
   assert(guard())
   local inspector=assert(X4LAN_MULTI_CREATE_INSPECTOR.new_x4({enabled=true,md_inspected=true,frame_confirmed=true,
    guard=guard,expected_save_path=cfg.authority_load_save_path,resolve=X4LAN_RESOLVE_STRING,
    timeout=cfg.authority_multi_create_timeout,position_tolerance=1.0}))
   local descriptors={}
   for i=1,2 do descriptors[i]={index=cfg.authority_multi_create_baseline+i,macro='ship_gen_m_tugboat_01_a_macro',
    owner='pioneers',sector=cfg['authority_multi_create_sector'..i],witness_index=cfg['authority_multi_create_witness'..i],
    seed=7183,x=-400,y=100000,z=500} end
   scenario=assert(X4LAN_MULTI_CREATE_SCENARIO.new({enabled=true,client=X4LAN_MULTI_CREATE_CLIENT,
    epoch=cfg.authority_multi_create_epoch,nonce=cfg.authority_multi_create_nonce,
    baseline=cfg.authority_multi_create_baseline,timeout=cfg.authority_multi_create_timeout,
    descriptors=descriptors,clock=GetCurRealTime,guard=guard,
    issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end,
    inspect=function(...)return inspector:inspect(...)end,
    emit=function(line)DebugError('[X4LAN] AUTH_MULTI_CREATE '..line)end}))
  end
  assert(scenario:tick())
 end)
 if not ok then fail() end
end
