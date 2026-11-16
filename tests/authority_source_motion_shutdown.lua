-- Pure Lua lifecycle with real bootstrap and sampler modules; no X4.
local B=dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local S=dofile('src/authority/lua/source_motion_sampler.lua')
local G=dofile('src/authority/lua/source_motion_shutdown.lua')
local epoch,nonce,gen=string.rep('a',32),string.rep('b',32),string.rep('c',32)
local function rig(options)
 options=options or {};local faults={};local requests={};local route_calls=0;local gate
 local bootstrap=assert(B.new({enabled=true,epoch=epoch,nonce=nonce,baseline=2,timeout=2,
  clock=function()return 1 end,guard=function()return true end,baseline_guard=function()return true end,
  issue=function(_,_,v)requests[#requests+1]=v;return true end,parse=function()return 1 end,
  inspect=function()return true end,complete=function()return true end}))
 local sampler=assert(S.new({enabled=true,epoch=epoch,generation=gen,nonce=nonce,max_tracks=2,scan_budget=1,
  interval=1,timeout=2,min_dt=.1,max_dt=1,clock=function()return 1 end,guard=function()return true end,
  binding_guard=function()return true end,actor_key=function()return '1' end,
  reader_factory=function()error('unexpected sample')end,fault=function()end}))
 gate=assert(G.new({enabled=true,bootstrap=bootstrap,sampler=sampler,
  guard=function()if options.guard_hook then options.guard_hook()end;return not options.guard_lost end,
  quiescent=function()if options.quiet_hook then options.quiet_hook()end;return not options.not_quiet end,
  route=function(value)route_calls=route_calls+1;if options.reenter_event then gate:event(value)end;return not options.route_failed end,
  fault=function(reason)faults[#faults+1]=reason end}))
 return gate,bootstrap,sampler,requests,faults,function()return route_calls end
end
-- A fixed diagnostic phase distinguishes guard, route and post-route failure.
for _,phase in ipairs({'guard_before','route','guard_after'})do
 local opts={route_failed=phase=='route'}
 local guards=0
 opts.guard_hook=function()
  guards=guards+1
  if phase=='guard_before' or (phase=='guard_after' and guards==2) then
   opts.guard_lost=true
  end
 end
 local g,_,_,_,faults=rig(opts)
 assert(not g:event('private payload') and g:state()=='failed' and faults[1]=='event')
 assert(g:diagnostic()==phase)
end
-- Idle stop really closes both components; event handler stays live and faults late events.
do
 local g,b,s,_,faults,calls=rig();assert(g:event('normal') and calls()==1)
 assert(g:stop() and g:state()=='stopped' and b:state()=='closed' and s:state()=='closed')
 assert(g:check());assert(not g:event('late') and g:state()=='failed' and faults[1]=='late_or_reentrant_event')
 assert(not g:check() and not g:stop() and #faults==1)
end
-- A dispatched bootstrap cannot be closed or hidden by STOP.
do
 local g,b,s,requests,faults=rig();assert(b:begin(1) and #requests==1)
 assert(not g:stop() and g:state()=='failed' and b:state()=='pending' and s:state()=='ready' and #faults==1)
 assert(not b:close() and b:state()=='failed')
end
-- Failure of either close and a non-quiescent owner must never acknowledge.
for _,bad in ipairs({'bootstrap','sampler','quiet','guard'})do
 local opts={not_quiet=bad=='quiet',guard_lost=bad=='guard'}
 local g,b,s,_,faults=rig(opts)
 if bad=='bootstrap' then b.close=function()return false end end
 if bad=='sampler' then s.close=function()return false end end
 assert(not g:stop() and g:state()=='failed' and #faults==1)
 if bad=='sampler' then assert(b:state()=='closed')end
end
-- A shutdown callback cannot silently invalidate the previously closed bootstrap.
do
 local g,b,s,_,faults=rig();local original=s.close
 s.close=function(self)b:begin(1);return original(self)end
 assert(not g:stop() and g:state()=='failed' and #faults==1)
end
-- Ongoing post-stop checks must notice newly pending external work.
do
 local opts={};local g=rig(opts);assert(g:stop() and g:check())
 opts.not_quiet=true;assert(not g:check() and g:state()=='failed')
end
-- Reentrant event during callback cannot be swallowed to authorize a stop/event.
do
 local g,_,_,_,faults=rig({reenter_event=true})
 assert(not g:event('x') and g:state()=='failed' and faults[1]=='late_or_reentrant_event')
end
do
 local g,b,_,_,faults=rig();local original=b.close
 b.close=function(self)g:event('reentrant');return original(self)end
 assert(not g:stop() and g:state()=='failed' and faults[1]=='late_or_reentrant_event')
end
-- check() is itself serialized: a swallowed nested call must still fault.
for _,from in ipairs({'guard','quiet'})do
 for _,method in ipairs({'event','stop','check'})do
  local opts={};local g,_,_,_,faults,calls=rig(opts)
  if from=='quiet' then assert(g:stop())end
  local original_calls=calls()
  opts[from=='guard' and 'guard_hook' or 'quiet_hook']=function()
   pcall(function() if method=='event' then g:event('nested') else g[method](g)end end)
  end
  assert(not g:check() and g:state()=='failed' and #faults==1 and calls()==original_calls)
 end
end
assert(G.new({enabled=false})==nil)
