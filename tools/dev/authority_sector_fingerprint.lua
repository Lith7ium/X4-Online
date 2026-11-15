-- Default-off read-only, paused identity evidence; the load probe owns updates.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_sector_fingerprint~=true then return end
local ffi=require('ffi');local C=ffi.C
local epoch,nonce=cfg.authority_sector_epoch,cfg.authority_fingerprint_nonce
assert(type(nonce)=='string' and #nonce==32 and nonce:match('^[0-9a-f]+$'))
local state='new';local failed=false;local last,start,settled,settled_game,pending
local initial_actor,initial_sector;local actors,sectors,values={},{},{};local n=0
local function log(s) DebugError('[X4LAN] AUTH_SECTOR_FINGERPRINT '..s) end
local function fail(s) if not failed then failed=true;state='failed';pending=nil;log('ERROR '..s) end end
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function observe()
 local p=C.GetSaveFolderPath()
 assert(p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 local real=GetCurRealTime();local game=tonumber(C.GetCurrentGameTime())
 assert(finite(real) and real>=0 and (not last or real>=last) and finite(game) and game>=0 and C.IsGamePaused())
 last=real;start=start or real;assert(real-start<=40)
 return real,game
end
local function live(a,s)
 assert(C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship'))
 assert(C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s)
end
local function token(v)
 return type(v)=='string' and #v>0 and #v<=128 and v~='null' and v~='nil' and v:match('^[%w_%-%.]+$')~=nil
end
local function send(slot)
 assert(not pending);local id=nonce..'-'..tostring(n+1)
 pending={id=id,slot=slot,deadline=last+5};state='wait'
 assert(AddUITriggeredEvent('X4AuthoritySectorFingerprint','Read',{epoch=epoch,slot=slot,request_id=id})~=false)
end
RegisterEvent('X4AuthoritySectorFingerprint.Refused',function() fail('refused') end)
RegisterEvent('X4AuthoritySectorFingerprint.Result',function(_,v)
 if failed then return end
 local ok=pcall(function()
  local now,game=observe();assert(state=='wait' and pending and now<=pending.deadline and game==settled_game)
  assert(type(v)=='string' and #v<=700)
  local id,ep,index,ah,sh,sc,sm,zc,zm=v:match('^([0-9a-f%-]+)|([0-9a-f]+)|([12])|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([^|]+)|([^|]+)|([^|]+)|([^|]+)$')
  assert(id==pending.id and ep==epoch and tonumber(index)==pending.slot)
  assert(token(sc) and token(sm) and token(zc) and token(zm))
  local a=X4LAN_RESOLVE_STRING.parse_hex(ah);local s=X4LAN_RESOLVE_STRING.parse_hex(sh);assert(a and s);live(a,s)
  local slot=pending.slot
  if slot==2 then assert(a==initial_actor and s==initial_sector) end
  local fingerprint=table.concat({sc,sm,zc,zm},'|')
  if actors[slot] then assert(actors[slot]==a and sectors[slot]==s and values[slot]==fingerprint)
  else actors[slot]=a;sectors[slot]=s;values[slot]=fingerprint end
  if actors[3-slot] then assert(actors[3-slot]~=a and sectors[3-slot]~=s) end
  local _,after=observe();assert(after==settled_game);live(a,s)
  n=n+1;pending=nil
  log(('ROW slot=%d n=%d ship_code=%s ship_macro=%s sector_code=%s sector_macro=%s game=%.17g'):format(slot,math.floor((n+1)/2),sc,sm,zc,zm,game))
  state=n==4 and 'done' or 'send'
  if state=='done' then log(('DONE samples=%d game=%.17g'):format(n,game)) end
 end)
 if not ok then fail('sample') end
end)
function X4LAN_SECTOR_FINGERPRINT_READY()
 if failed then error('sector fingerprint failed') end
 local ok=pcall(function()
  local now,game=observe()
  if pending then assert(now<=pending.deadline) end
  if state=='new' then
   local initial_game,initial_order;initial_actor,initial_sector,initial_order,initial_game=X4LAN_SECTOR_READ_EXPORT()
   assert(initial_game==game);live(initial_actor,initial_sector);settled=now;settled_game=game;state='settle'
  elseif state=='settle' then assert(game==settled_game);if now-settled>=0.1 then state='send' end
  elseif state=='send' then assert(game==settled_game);send(n%2+1)
  elseif state=='wait' then assert(game==settled_game)
  elseif state~='done' then error('invalid state') end
 end)
 if not ok then fail('state');error('sector fingerprint failed') end
 return state=='done'
end
