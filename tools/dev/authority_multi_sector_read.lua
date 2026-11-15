-- Default-off isolated read diagnostic; the load probe exclusively owns updates.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_multi_sector_read~=true then return end
local ffi=require('ffi');local C=ffi.C
local epoch,nonce=cfg.authority_sector_epoch,cfg.authority_multi_nonce
assert(type(nonce)=='string' and #nonce==32 and nonce:match('^[0-9a-f]+$'))
assert(type(Pause)=='function' and type(Unpause)=='function')
local state='new';local failed=false;local last,start,pending,settled,settled_game,due
local actors,sectors={},{};local counts={0,0};local n=0
local initial_actor,initial_sector
local function log(s) DebugError('[X4LAN] AUTH_MULTI_SECTOR '..s) end
local function fail(s) if not failed then failed=true;state='failed';pending=nil;log('ERROR '..s) end end
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function observe()
 local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 local t=GetCurRealTime();local g=tonumber(C.GetCurrentGameTime())
 assert(finite(t) and t>=0 and (not last or t>=last) and finite(g) and g>=0)
 last=t;start=start or t;assert(t-start<=40)
 return t,g,C.IsGamePaused()
end
local function live(a,s)
 assert(C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship'))
 assert(C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s)
end
local function send(slot)
 assert(not pending);local id=nonce..'-'..tostring(n+1)
 pending={id=id,slot=slot,deadline=last+5}
 state='wait'
 local sent=AddUITriggeredEvent('X4AuthorityMultiSectorRead','Read',{epoch=epoch,slot=slot,request_id=id})
 assert(sent~=false)
end
RegisterEvent('X4AuthorityMultiSectorRead.Refused',function() fail('refused') end)
RegisterEvent('X4AuthorityMultiSectorRead.Result',function(_,v)
 if failed then return end
 local ok=pcall(function()
  local before,game,paused=observe();assert(state=='wait' and pending and not paused and before<=pending.deadline)
  assert(type(v)=='string' and #v<=200)
  local id,ep,index,actor_hex,sector_hex=v:match('^([0-9a-f%-]+)|([0-9a-f]+)|([12])|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)$')
  assert(id==pending.id and ep==epoch and tonumber(index)==pending.slot)
  local slot=pending.slot;local a=X4LAN_RESOLVE_STRING.parse_hex(actor_hex);local s=X4LAN_RESOLVE_STRING.parse_hex(sector_hex)
  assert(a and s);live(a,s)
  if slot==2 then assert(a==initial_actor and s==initial_sector) end
  if actors[slot] then assert(actors[slot]==a and sectors[slot]==s) else actors[slot]=a;sectors[slot]=s end
  if actors[3-slot] then assert(actors[3-slot]~=a and sectors[3-slot]~=s) end
  local p=C.GetObjectPositionInSector(a)
  local after,game_after,paused_after=observe();assert(not paused_after and game_after>=game);live(a,s)
  local x,y,z=tonumber(p.x),tonumber(p.y),tonumber(p.z);assert(finite(x) and finite(y) and finite(z))
  counts[slot]=counts[slot]+1;n=n+1;pending=nil
  log(('SAMPLE slot=%d n=%d real_before=%.17g real_after=%.17g game_before=%.17g game_after=%.17g x=%.17g y=%.17g z=%.17g'):format(slot,counts[slot],before,after,game,game_after,x,y,z))
  if n==6 then state='pause_request' else due=after+0.25;state='sampling' end
 end)
 if not ok then fail('sample') end
end)
function X4LAN_MULTI_SECTOR_READY()
 if failed then error('multi-sector read failed') end
 local ok=pcall(function()
  local now,game,paused=observe()
  if pending then assert(now<=pending.deadline) end
  if state=='new' then
   assert(paused);local initial_game;initial_actor,initial_sector,initial_game=X4LAN_MULTI_SECTOR_INITIAL()
   assert(initial_game==game);live(initial_actor,initial_sector)
   settled=now;settled_game=game;state='settle'
  elseif state=='settle' then
   assert(paused and game==settled_game)
   if now-settled>=0.1 then Unpause();state='resume_wait' end
  elseif state=='resume_wait' then
   assert(game>=settled_game)
   if not paused and game>settled_game then due=now;state='sampling' end
  elseif state=='sampling' then assert(not paused);if now>=due then send(n%2+1) end
  elseif state=='wait' then assert(not paused)
  elseif state=='pause_request' then assert(not paused);Pause();state='pause_wait'
  elseif state=='pause_wait' then if paused then settled=now;settled_game=game;state='pause_settle' end
  elseif state=='pause_settle' then
   assert(paused and game==settled_game)
   if now-settled>=0.1 then state='done';log(('DONE samples=%d game=%.17g'):format(n,game)) end
  elseif state~='done' then error('invalid state') end
 end)
 if not ok then fail('state');error('multi-sector read failed') end
 return state=='done'
end
