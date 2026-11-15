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
local function shape(v)
 if type(v)~='string' then return type(v) end
 if v=='null' or v=='nil' then return v end
 if #v==0 then return 'empty' end
 if #v>128 then return 'too_long' end
 if not v:match('^[%w_%-%.]+$') then return 'invalid_chars' end
 return 'token'
end
local function send(slot)
 assert(not pending);local id=nonce..'-'..tostring(n+1)
 pending={id=id,slot=slot,deadline=last+5};state='wait'
 assert(AddUITriggeredEvent('X4AuthoritySectorFingerprint','Read',{epoch=epoch,slot=slot,request_id=id})~=false)
end
RegisterEvent('X4AuthoritySectorFingerprint.Refused',function() fail('refused') end)
RegisterEvent('X4AuthoritySectorFingerprint.Result',function(_,v)
 if failed then return end
 local stage,detail='observe',nil
 local ok=pcall(function()
  local now,game=observe();stage='pending';assert(state=='wait' and pending and now<=pending.deadline and game==settled_game)
  stage='row_type';assert(type(v)=='string' and #v<=700)
  stage='row_format';local _,pipes=v:gsub('|','');detail='bytes_'..#v..'_separators_'..pipes
  local id,ep,index,ah,sh,sc,sm,zm=v:match('^([0-9a-f%-]+)|([0-9a-f]+)|([12])|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([^|]+)|([^|]+)|([^|]+)$')
  assert(id);detail=nil
  stage='request_id';assert(id==pending.id)
  stage='epoch';assert(ep==epoch)
  stage='slot';assert(tonumber(index)==pending.slot)
  for _,field in ipairs({{'ship_code',sc},{'ship_macro',sm},{'sector_macro',zm}}) do
   stage=field[1];detail='shape_'..shape(field[2]);assert(token(field[2]));detail=nil
  end
  stage='handle_parse';local a=X4LAN_RESOLVE_STRING.parse_hex(ah);local s=X4LAN_RESOLVE_STRING.parse_hex(sh);assert(a and s)
  stage='local_binding';live(a,s)
  local slot=pending.slot
  stage='initial_binding';if slot==2 then assert(a==initial_actor and s==initial_sector) end
  local fingerprint=table.concat({sc,sm,zm},'|')
  stage='repeat_binding'
  if actors[slot] then assert(actors[slot]==a and sectors[slot]==s and values[slot]==fingerprint)
  else actors[slot]=a;sectors[slot]=s;values[slot]=fingerprint end
  stage='distinct_binding'
  if actors[3-slot] then assert(actors[3-slot]~=a and sectors[3-slot]~=s) end
  stage='final_observe'
  local _,after=observe();assert(after==settled_game);live(a,s)
  n=n+1;pending=nil
  log(('ROW slot=%d n=%d ship_code=%s ship_macro=%s sector_macro=%s game=%.17g'):format(slot,math.floor((n+1)/2),sc,sm,zm,game))
  state=n==4 and 'done' or 'send'
  if state=='done' then log(('DONE samples=%d game=%.17g'):format(n,game)) end
 end)
 if not ok then fail('sample_'..stage..(detail and (' '..detail) or '')) end
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
