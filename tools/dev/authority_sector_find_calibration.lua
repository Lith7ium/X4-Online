-- Default-off read-only local diagnostic. The load probe exclusively owns updates.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_sector_find_calibration~=true then return end
local ffi=require('ffi');local C=ffi.C
local epoch,nonce=cfg.authority_sector_epoch,cfg.authority_sector_find_nonce
local macros=cfg.authority_sector_find_macros
assert(type(nonce)=='string' and #nonce==32 and nonce:match('^[0-9a-f]+$'))
assert(type(macros)=='table' and #macros==2 and macros[1]~=macros[2])
for i=1,2 do assert(type(macros[i])=='string' and #macros[i]<=128 and macros[i]:match('^[%w_%-%.]+$')) end
local state,failed='new',false
local last,start,game0,pending,initial_actor,initial_sector=nil,nil,nil,nil,nil,nil
local actors,sectors={},{};local n=0
local function log(s) DebugError('[X4LAN] AUTH_SECTOR_FIND '..s) end
local function fail(s) if not failed then failed=true;state='failed';pending=nil;log('ERROR '..s) end end
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function observe()
 local p=C.GetSaveFolderPath()
 assert(p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 local t=GetCurRealTime();local g=tonumber(C.GetCurrentGameTime())
 assert(finite(t) and t>=0 and (not last or t>=last) and finite(g) and g>=0 and C.IsGamePaused())
 last=t;start=start or t;assert(t-start<=40)
 return t,g
end
local function live(a,s)
 assert(C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship'))
 assert(C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s)
end
RegisterEvent('X4AuthoritySectorFindCalibration.Refused',function() fail('refused') end)
RegisterEvent('X4AuthoritySectorFindCalibration.Result',function(_,v)
 if failed then return end
 local ok=pcall(function()
  local now,game=observe();assert(state=='wait' and pending and now<=pending.deadline and game==game0)
  assert(type(v)=='string' and #v<=700)
  local id,ep,slot,ah,sh,fh,macro=v:match('^([0-9a-f%-]+)|([0-9a-f]+)|([12])|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([%w_%-%.]+)$')
  assert(id==pending.id and ep==epoch and tonumber(slot)==pending.slot and macro==macros[pending.slot])
  local a=X4LAN_RESOLVE_STRING.parse_hex(ah);local s=X4LAN_RESOLVE_STRING.parse_hex(sh);local f=X4LAN_RESOLVE_STRING.parse_hex(fh)
  assert(a and s and f and s==f);live(a,s)
  if pending.slot==2 then assert(a==initial_actor and s==initial_sector) end
  if sectors[3-pending.slot] then assert(sectors[3-pending.slot]~=s and actors[3-pending.slot]~=a) end
  actors[pending.slot]=a;sectors[pending.slot]=s
  local _,after=observe();assert(after==game0);live(a,f)
  n=n+1;log(('ROW slot=%d sector_macro=%s game=%.17g'):format(pending.slot,macro,game));pending=nil
  if n==2 then state='done';log(('DONE samples=2 game=%.17g'):format(game)) else state='send' end
 end)
 if not ok then fail('result') end
end)
function X4LAN_SECTOR_FIND_CALIBRATION_READY()
 if failed then error('sector find calibration failed') end
 local ok=pcall(function()
  local now,game=observe()
  if pending then assert(now<=pending.deadline) end
  if state=='new' then
   local order,initial_game;initial_actor,initial_sector,order,initial_game=X4LAN_SECTOR_READ_EXPORT()
   assert(initial_game==game);live(initial_actor,initial_sector);game0=game;state='send'
  elseif state=='send' then
   assert(game==game0);local slot=n+1;pending={id=nonce..'-'..tostring(slot),slot=slot,deadline=now+5};state='wait'
   assert(AddUITriggeredEvent('X4AuthoritySectorFindCalibration','Read',{epoch=epoch,slot=slot,request_id=pending.id,macro=macros[slot]})~=false)
  elseif state=='wait' then assert(game==game0)
  else assert(state=='done' and game==game0) end
 end)
 if not ok then fail('state');error('sector find calibration failed') end
 return state=='done'
end
