-- Opt-in load admission primitive. Importing this file performs no game calls.
-- The caller supplies an X4 adapter and a process-private, immutable attempt config.
-- A separate trusted supervisor must verify ordered events and process continuity.
local M={}
local fields={'world_epoch','connection_handle','baseline_id','load_generation',
 'checkpoint_id','sha256','attempt_id','slot'}
local function valid_ticket(t)
 if type(t)~='table' then return false end
 local count=0
 for k in pairs(t) do
  local found=false
  for _,name in ipairs(fields) do if k==name then found=true;break end end
  if not found then return false end
  count=count+1
 end
 if count~=#fields then return false end
 local function integer(x) return type(x)=='number' and x==math.floor(x) and x>=1 and x<=9007199254740991 end
 return type(t.world_epoch)=='string' and #t.world_epoch>=1 and #t.world_epoch<=64
  and t.world_epoch:match('^[A-Za-z0-9_-]+$')~=nil
  and integer(t.connection_handle) and integer(t.baseline_id) and integer(t.load_generation)
  and type(t.checkpoint_id)=='string' and t.checkpoint_id:match('^checkpoint%-[0-9a-f]+$')~=nil and #t.checkpoint_id==43
  and type(t.sha256)=='string' and t.sha256:match('^[0-9a-f]+$')~=nil and #t.sha256==64
  and type(t.attempt_id)=='string' and t.attempt_id:match('^[0-9a-f]+$')~=nil and #t.attempt_id==32
  and type(t.slot)=='string' and t.slot:match('^save_%d%d%d$')~=nil
end
local function copy(t) local c={};for _,k in ipairs(fields) do c[k]=t[k] end;return c end
function M.new(cfg,engine,emit)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 assert(type(engine)=='table' and type(emit)=='function','missing dependencies')
 for _,k in ipairs({'in_startmenu','save_available','load','player_valid','is_paused','pause'}) do
  assert(type(engine[k])=='function','missing engine method '..k)
 end
 assert(valid_ticket(cfg.ticket),'invalid configured load attempt')
 local state='idle';local ticket=copy(cfg.ticket);local pause_requested=false
 local obj={}
 function obj.begin()
  assert(state=='idle','already active')
  assert(engine.in_startmenu()==true,'load requires start menu')
  assert(engine.save_available(ticket.slot)==true,'save unavailable')
  state='load_requested'
  -- This is not a success receipt. The external supervisor must witness this
  -- before it can establish continuity across the Lua reset caused by load.
  emit('load_requested',copy(ticket))
  engine.load(ticket.slot)
 end
 -- A fresh UI state recovers the configured ticket, not the earlier Lua state.
 -- Only the external supervisor can correlate ordered events in the same process.
 function obj.observe_pause()
  assert(state=='idle','already active')
  state='waiting_for_pause'
 end
 function obj.update()
  if state~='waiting_for_pause' then return false end
  if engine.in_startmenu()~=false or engine.player_valid()~=true then return false end
  if engine.is_paused()~=true then
   if not pause_requested then pause_requested=true;engine.pause() end
   return false
  end
  -- Recheck the player after observing pause; never resume the client here.
  if engine.in_startmenu()~=false or engine.player_valid()~=true then return false end
  state='observed';emit('pause_observed',copy(ticket));return true
 end
 return obj
end
X4LAN_AUTHORITY_CLIENT_LOAD_BARRIER=M
return M
