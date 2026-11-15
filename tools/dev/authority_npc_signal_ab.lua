-- One isolated existing-NPC experiment, called by the existing update owner.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_npc_signal_ab~=true then return end
local ffi=require('ffi');local C=ffi.C
local epoch,nonce,mode=cfg.authority_sector_epoch,cfg.authority_npc_velocity_nonce,cfg.authority_npc_signal_mode
assert(mode=='control' or mode=='treatment')
assert(type(nonce)=='string' and #nonce==32 and nonce:match('^[0-9a-f]+$'))
local state='new';local failed=false;local started,last,settled,settled_game,pending,actor,sector,initial_order
local initial_state
local phase,anchor,due='before',nil,nil;local counts={before=0,during=0,after=0,tail=0};local n=0
local function log(s) DebugError('[X4LAN] AUTH_NPC_SIGNAL_AB '..s) end
local function fail(s) if not failed then failed=true;state='failed';pending=nil;log('ERROR '..s) end end
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function observe()
 local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 local real=GetCurRealTime();local game=tonumber(C.GetCurrentGameTime())
 assert(finite(real) and real>=0 and (not last or real>=last) and finite(game) and game>=0)
 last=real;started=started or real;assert(real-started<=240)
 return real,game,C.IsGamePaused()
end
local function live()
 assert(actor and sector and C.IsValidComponent(actor) and C.IsComponentOperational(actor) and C.IsComponentClass(actor,'ship'))
 assert(C.GetContextByClass(actor,'sector',false)==sector)
end
local function send(op)
 assert(not pending);n=n+1;local id=nonce..'-'..n
 pending={id=id,op=op,deadline=last+5}
 local sent=AddUITriggeredEvent('X4AuthorityNPCSignalAB',op,{epoch=epoch,request_id=id,phase=phase,mode=mode})
 assert(sent~=false)
end
local function check(row,op,paused)
 local now,game,ispaused=observe();assert(ispaused==paused and pending and pending.op==op and now<=pending.deadline)
 assert(type(row)=='string' and #row<=240);live()
 local id,hex,order,orderstate,found,outcome
 if op=='Begin' then
  id,order,orderstate,hex=row:match('^([0-9a-f%-]+)|([%w_%-]+)|([a-z]+)|(0[xX][0-9a-fA-F]+)$')
  assert(order==initial_order and (orderstate=='started' or orderstate=='critical'));initial_state=orderstate
 elseif op=='Sample' then
  id,found,hex,order,orderstate=row:match('^([0-9a-f%-]+)|([a-z]+)|(0[xX][0-9a-fA-F]+)|([%w_%-]+)|([a-z]+)$')
  assert(found==phase and (orderstate=='started' or orderstate=='critical' or orderstate=='other' or orderstate=='none'))
  assert((order=='none')==(orderstate=='none'))
 elseif op=='Decision' then
  id,found,outcome,order,orderstate,hex=row:match('^([0-9a-f%-]+)|([a-z]+)|([a-z_]+)|([%w_%-]+)|([a-z]+)|(0[xX][0-9a-fA-F]+)$')
  assert(found==mode and ((mode=='control' and outcome=='noop') or (mode=='treatment' and (outcome=='sent' or outcome=='skipped_order'))))
  assert((orderstate=='started' or orderstate=='critical' or orderstate=='other' or orderstate=='none') and (order=='none')==(orderstate=='none'))
  if outcome=='sent' then assert(order==initial_order and orderstate==initial_state) end
 else id,hex=row:match('^([0-9a-f%-]+)|(0[xX][0-9a-fA-F]+)$') end
 assert(id==pending.id and hex and X4LAN_RESOLVE_STRING.parse_hex(hex)==actor)
 pending=nil;return now,game,order,orderstate,outcome
end
local function safe(fn,reason) if not failed then local ok=pcall(fn);if not ok then fail(reason) end end end
RegisterEvent('X4AuthorityNPCSignalAB.Refused',function() fail('refused') end)
RegisterEvent('X4AuthorityNPCSignalAB.Began',function(_,row)
 safe(function()
  local _,game=check(row,'Begin',true);assert(state=='begin_wait' and game==settled_game)
  log(('BEGAN mode=%s order=%s order_state=%s game=%.17g'):format(mode,initial_order,initial_state,game));state='resume'
 end,'begin')
end)
RegisterEvent('X4AuthorityNPCSignalAB.Sampled',function(_,row)
 safe(function()
  local _,before,order,orderstate=check(row,'Sample',false);assert(state=='sample_wait' and before>=anchor)
  local p=C.GetObjectPositionInSector(actor);local real,after,paused=observe();assert(not paused and after>=before);live()
  local x,y,z=tonumber(p.x),tonumber(p.y),tonumber(p.z);assert(finite(x) and finite(y) and finite(z))
  counts[phase]=counts[phase]+1
  log(('SAMPLE phase=%s n=%d pilot=same order=%s order_state=%s real=%.17g game_before=%.17g game_after=%.17g x=%.17g y=%.17g z=%.17g'):format(
   phase,counts[phase],order,orderstate,real,before,after,x,y,z))
  if phase=='before' and (order~=initial_order or orderstate~=initial_state) then fail('order_changed_before_apply');return end
  local limit=(phase=='before' or phase=='during') and 3 or 5
  if counts[phase]<limit then due=after+((phase=='before' or phase=='during') and 1 or 5);state='sampling'
  elseif phase=='before' then state='apply'
  elseif phase=='during' then state='release'
  elseif phase=='after' then state='decision'
  else state='pause_request' end
 end,'sample')
end)
for _,entry in ipairs({{'Applied','Apply','during'},{'Released','Release','after'}}) do
 local event,op,next_phase=unpack(entry)
 RegisterEvent('X4AuthorityNPCSignalAB.'..event,function(_,row)
  safe(function()
   local _,game=check(row,op,false);assert(state==op:lower()..'_wait')
   phase=next_phase;anchor=game;due=game+(next_phase=='after' and 5 or 1)
   log(('%s game=%.17g'):format(event:upper(),game));state='sampling'
  end,op:lower())
 end)
end
RegisterEvent('X4AuthorityNPCSignalAB.Decided',function(_,row)
 safe(function()
  local _,game,order,orderstate,outcome=check(row,'Decision',false);assert(state=='decision_wait')
  log(('DECISION mode=%s outcome=%s order=%s order_state=%s game=%.17g'):format(mode,outcome,order,orderstate,game))
  phase='tail';anchor=game;due=game+5;state='sampling'
 end,'decision')
end)
function X4LAN_NPC_SIGNAL_AB_READY()
 if failed then error('NPC constant velocity failed') end
 local ok=pcall(function()
  local now,game,paused=observe()
  if pending then assert(now<=pending.deadline) end
  if state=='new' then
   local initial_game;assert(paused)
   actor,sector,initial_order,initial_game=X4LAN_SECTOR_READ_EXPORT()
   assert(initial_game==game and type(initial_order)=='string' and initial_order~='none');live()
   settled=now;settled_game=game;state='settle'
  elseif state=='settle' then
   assert(paused and game==settled_game);live()
   if now-settled>=0.1 then state='begin_wait';send('Begin') end
  elseif state=='begin_wait' then assert(paused and game==settled_game)
  elseif state=='resume' then assert(paused and game==settled_game);Unpause();state='resume_wait'
  elseif state=='resume_wait' then
   if not paused and game>settled_game then phase='before';anchor=game;due=game+1;state='sampling' end
  elseif state=='sampling' then
   assert(not paused);live();if game>=due then state='sample_wait';send('Sample') end
  elseif state=='sample_wait' then assert(not paused)
  elseif state=='apply' then assert(not paused);state='apply_wait';send('Apply')
  elseif state=='release' then assert(not paused);state='release_wait';send('Release')
  elseif state=='decision' then assert(not paused);state='decision_wait';send('Decision')
  elseif state=='apply_wait' or state=='release_wait' or state=='decision_wait' then assert(not paused)
  elseif state=='pause_request' then assert(not paused);Pause();state='pause_wait'
  elseif state=='pause_wait' then if paused then settled=now;settled_game=game;state='pause_settle' end
  elseif state=='pause_settle' then
   assert(paused and game==settled_game)
   if now-settled>=0.1 then state='done';log(('DONE mode=%s before=%d during=%d after=%d tail=%d game=%.17g'):format(mode,counts.before,counts.during,counts.after,counts.tail,game)) end
  elseif state~='done' then error('invalid state') end
 end)
 if not ok then fail('state');error('NPC constant velocity failed') end
 return state=='done'
end
