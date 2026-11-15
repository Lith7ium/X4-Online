-- Disposable, single-owner control/treatment case. Never registers an update callback.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_sector_jobs_case~=true then return end
local ffi=require('ffi');local C=ffi.C
local mode,epoch,nonce=cfg.authority_jobs_mode,cfg.authority_sector_epoch,cfg.authority_jobs_nonce
local min_game=cfg.authority_jobs_min_game
assert((mode=='control' or mode=='treatment') and type(nonce)=='string' and #nonce==32 and nonce:match('^[0-9a-f]+$'))
assert(type(min_game)=='number' and min_game>=1 and min_game<=30 and min_game==min_game)
assert(cfg.authority_sector_slot==2 and type(Pause)=='function' and type(Unpause)=='function')
local state='new';local failed=false;local started,last_real,settled,settled_game,pending,actor,sector,order,last_game
local samples=0;local due
local function log(s) DebugError('[X4LAN] AUTH_JOBS_CASE '..s) end
local function fail(s) if not failed then failed=true;state='failed';log('ERROR '..s) end end
local function number(v) return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function observe()
 local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 local now=GetCurRealTime();local game=tonumber(C.GetCurrentGameTime())
 assert(number(now) and now>=0 and (not last_real or now>=last_real) and number(game) and game>=0)
 last_real=now;started=started or now;assert(now-started<=40)
 return now,game,C.IsGamePaused()
end
local function live_actor()
 assert(actor and sector and C.IsValidComponent(actor) and C.IsComponentOperational(actor) and C.IsComponentClass(actor,'ship'))
 assert(C.GetContextByClass(actor,'sector',false)==sector)
end
local function send(op,request_id)
 assert(not pending);pending={id=request_id,op=op,deadline=last_real+5}
 local ok=AddUITriggeredEvent('X4AuthoritySectorJobsCorrelated',op,{epoch=epoch,slot=2,mode=mode,request_id=request_id})
 assert(ok~=false)
end
local function match(value,op)
 assert(pending and pending.op==op and type(value)=='string')
 local id,found,hex,order_state
 if op=='Begin' then id,found,hex=value:match('^([0-9a-f%-]+)|([%w_%-]+)|(0[xX][0-9a-fA-F]+)$')
 else
  id,found,hex,order_state=value:match('^([0-9a-f%-]+)|([%w_%-]+)|(0[xX][0-9a-fA-F]+)|([a-z]+)$')
  assert(order_state=='started' or order_state=='critical')
 end
 local resolved=hex and X4LAN_RESOLVE_STRING.parse_hex(hex)
 assert(id==pending.id and found==order and resolved and resolved==actor);pending=nil
 return order_state
end
local function safe(fn,reason)
 if failed then return end
 local ok=pcall(fn)
 if not ok then fail(reason) end
end
RegisterEvent('X4AuthoritySectorJobsCorrelated.Refused',function() fail('refused') end)
RegisterEvent('X4AuthoritySectorJobsCorrelated.Began',function(_,value)
 safe(function()
  local now,game,paused=observe();assert(paused and state=='begin_wait' and pending and now<=pending.deadline)
  live_actor();match(value,'Begin');assert(game==settled_game)
  log(('BEGAN mode=%s order=%s game=%.17g'):format(mode,order,game));state='resume'
 end,'begin')
end)
RegisterEvent('X4AuthoritySectorJobsCorrelated.Sampled',function(_,value)
 safe(function()
  local now,game,paused=observe();assert(not paused and state=='sample_wait' and pending and now<=pending.deadline)
  live_actor();local order_state=match(value,'Sample');assert(game>last_game)
  local pos=C.GetObjectPositionInSector(actor);local after_now,after_game,after_paused=observe()
  live_actor();assert(not after_paused and after_game>=game)
  local x,y,z=tonumber(pos.x),tonumber(pos.y),tonumber(pos.z)
  assert(number(x) and number(y) and number(z));samples=samples+1;last_game=after_game
  log(('SAMPLE n=%d pilot=same order=%s order_state=%s real=%.17g game_before=%.17g game_after=%.17g x=%.17g y=%.17g z=%.17g'):format(samples,order,order_state,after_now,game,after_game,x,y,z))
  if samples>=6 then state='pause_request' else due=after_now+0.25;state='sampling' end
 end,'sample')
end)
function X4LAN_JOBS_CASE_READY()
 if failed then error('jobs case failed') end
 local ok=pcall(function()
  local now,game,paused=observe()
  if pending then assert(now<=pending.deadline) end
  if state=='new' then
   local initial_game
   assert(paused);actor,sector,order,initial_game=X4LAN_SECTOR_READ_EXPORT()
   assert(number(initial_game) and initial_game==game)
   assert(type(order)=='string' and order~='none');live_actor();settled=now;settled_game=game;state='settle'
  elseif state=='settle' then
   assert(paused and game==settled_game);live_actor()
   if now-settled>=0.1 then state='begin_wait';send('Begin',nonce..'-0') end
  elseif state=='begin_wait' then assert(paused and game==settled_game)
  elseif state=='resume' then assert(paused and game==settled_game);live_actor();Unpause();state='resume_wait'
  elseif state=='resume_wait' then
   assert(game>=settled_game)
   if not paused and game>settled_game then last_game=settled_game;due=now;state='sampling' end
  elseif state=='sampling' then
   assert(not paused and game>=last_game);live_actor()
   if now>=due and game>=settled_game+min_game*(samples+1)/6 then
    state='sample_wait';send('Sample',nonce..'-'..tostring(samples+1))
   end
  elseif state=='sample_wait' then assert(not paused and game>=last_game);live_actor()
  elseif state=='pause_request' then assert(not paused and game>=last_game);live_actor();Pause();state='pause_wait'
  elseif state=='pause_wait' then
   assert(game>=last_game);live_actor()
   if paused then settled=now;settled_game=game;state='pause_settle' end
  elseif state=='pause_settle' then
   assert(paused and game==settled_game);live_actor()
   if now-settled>=0.1 then state='done';log(('DONE mode=%s samples=%d game=%.17g'):format(mode,samples,game)) end
  elseif state~='done' then error('invalid state') end
 end)
 if not ok then fail('state');error('jobs case failed') end
 return state=='done'
end
