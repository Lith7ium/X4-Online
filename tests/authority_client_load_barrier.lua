local M=assert(loadfile('src/authority/lua/client_load_barrier.lua'))()
local adapter=assert(loadfile('src/authority/lua/x4_client_load_engine.lua'))()
assert(M.new({},nil,nil)==nil and adapter.new({})==nil)
local E={menu=true,valid=false,paused=false,pause_calls=0,loads=0,available=true}
local engine={
 in_startmenu=function() return E.menu end,
 save_available=function(slot) return E.available and slot=='save_009' end,
 load=function(slot) assert(slot=='save_009');E.loads=E.loads+1 end,
 player_valid=function() return E.valid end,
 is_paused=function() return E.paused end,
 pause=function() E.pause_calls=E.pause_calls+1 end,
}
local ticket={world_epoch='epoch-1',connection_handle=1,baseline_id=2,load_generation=3,
 checkpoint_id='checkpoint-'..string.rep('a',32),sha256=string.rep('b',64),
 attempt_id=string.rep('c',32),slot='save_009'}
local events={}
local function emit(kind,t) events[#events+1]={kind=kind,t=t} end
local function fail(f) assert(not pcall(f)) end
local cfg={enabled=true,ticket=ticket}
local first=M.new(cfg,engine,emit)
E.available=false;fail(function() first.begin() end);assert(#events==0 and E.loads==0)
E.available=true;first.begin();assert(#events==1 and events[1].kind=='load_requested' and E.loads==1)
assert(not first.update());fail(function() first.begin() end)
-- Config survives reload, but the caller must independently correlate the
-- ordered messages from the same supervised process. No load success is claimed.
local second=M.new(cfg,engine,emit)
second.observe_pause();assert(not second.update() and E.pause_calls==0 and #events==1)
E.menu=false;assert(not second.update() and E.pause_calls==0 and #events==1)
E.valid=true;assert(not second.update() and E.pause_calls==1)
assert(not second.update() and E.pause_calls==1 and #events==1)
E.paused=true;assert(second.update() and #events==2)
assert(events[2].kind=='pause_observed' and events[2].t.attempt_id==ticket.attempt_id)
assert(not second.update() and #events==2);fail(function() second.observe_pause() end)
-- Ticket fields and numeric identities must be exact.
local bad={};for k,v in pairs(ticket) do bad[k]=v end;bad.extra=true
E.menu=true
fail(function() M.new({enabled=true,ticket=bad},engine,emit) end)
bad.extra=nil;bad.load_generation=0
fail(function() M.new({enabled=true,ticket=bad},engine,emit) end)
print('client load barrier checks passed')
