-- Private running experiment. The pre-existing load owner owns onUpdate.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_multi_create_running~=true then return end
local ffi=require('ffi')
ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
local C=ffi.C
local failed=false;local phase='initial';local game_last=nil;local game_start=nil;local saw_unpaused=false
local client,inspector,deadline,settle,created_time
local function fail()if not failed then failed=true;DebugError('[X4LAN] AUTH_MULTI_RUNNING ERROR') end end
local function time()
 local g=tonumber(C.GetCurrentGameTime())
 if not g or g~=g or g<0 or g==math.huge or (game_last and g<game_last) then return nil end
 game_last=g;return g
end
local function profile()
 local p=C.GetSaveFolderPath()
 return p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_load_save_path and C.IsPlayerValid()
end
local function guard()
 return profile() and not C.IsGamePaused() and time()~=nil
end
local function emit(line)DebugError('[X4LAN] AUTH_MULTI_RUNNING '..line)end
local delivered=nil
assert(RegisterEvent('X4AuthorityMultiCreateReceiver.Result',function(_,value)
 if failed or not client or delivered then fail();return end
 local ok,accepted=pcall(client.event,client,value)
 if not ok or accepted~=true or not guard() then fail();return end
 if delivered then
  if phase=='initializing' and delivered=='initialize' then phase='ready'
  elseif phase=='creating' and delivered=='create' then
   created_time=time();if not created_time then fail();return end
   emit('ROW create '..(cfg.authority_multi_create_baseline+1)..' '..cfg.authority_multi_create_sector1..' '..string.format('%.17g',created_time))
   phase='settling';settle=GetCurRealTime()
  else fail();return end
  delivered=nil
 end
end)~=false)
function X4LAN_MULTI_CREATE_RUN_TICK()
 if failed then return end
 local ok=pcall(function()
  local now=GetCurRealTime();assert(type(now)=='number' and now==now and now>=0 and now<math.huge)
  if not deadline then deadline=now+cfg.authority_multi_create_timeout end
  assert(now<deadline and profile())
  if phase=='initial' then
   assert(C.IsGamePaused());game_start=assert(time());phase='resuming';Unpause();return
  end
  if phase=='resuming' then
   if C.IsGamePaused() then assert(not saw_unpaused);return end
   saw_unpaused=true
   local g=assert(time());if g<=game_start then return end
   emit('RUNNING '..string.format('%.17g',game_start)..' '..string.format('%.17g',g))
   inspector=assert(X4LAN_MULTI_CREATE_INSPECTOR.new_x4({enabled=true,running=true,md_inspected=true,frame_confirmed=true,
    guard=guard,expected_save_path=cfg.authority_load_save_path,resolve=X4LAN_RESOLVE_STRING,
    timeout=cfg.authority_multi_create_timeout,position_tolerance=2.0}))
   client=assert(X4LAN_MULTI_CREATE_CLIENT.new({enabled=true,epoch=cfg.authority_multi_create_epoch,
    nonce=cfg.authority_multi_create_nonce,baseline=cfg.authority_multi_create_baseline,
    timeout=cfg.authority_multi_create_timeout,clock=GetCurRealTime,guard=guard,
    issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end,
    inspect=function(...)return inspector:inspect(...)end,
    complete=function(kind,result)
     if delivered or (phase=='initializing' and (kind~='initialize' or result.epoch~=cfg.authority_multi_create_epoch)) or
      (phase=='creating' and (kind~='create' or result.index~=cfg.authority_multi_create_baseline+1)) or
      (phase~='initializing' and phase~='creating') then return false end
     delivered=kind;return true
    end}))
   phase='initializing';assert(client:initialize());return
  end
  assert(guard() and client:tick())
  if phase=='ready' then
   assert(inspector:arm_running())
   phase='creating';assert(client:create({index=cfg.authority_multi_create_baseline+1,
    macro='ship_gen_m_tugboat_01_a_macro',owner='pioneers',sector=cfg.authority_multi_create_sector1,
    witness_index=cfg.authority_multi_create_witness1,seed=7183,x=-400,y=100000,z=500}));return
  end
  if phase=='settling' and now-settle>=0.5 then
   local g=assert(time());if g<=created_time then return end
   emit('DONE '..string.format('%.17g',g));phase='done'
  end
 end)
 if not ok then fail() end
end
