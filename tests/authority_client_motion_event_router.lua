local M=dofile('src/authority/lua/client_motion_event_router.lua');assert(M.new({enabled=false})==nil)
local n1,n2,g1,g2,e=('1'):rep(32),('2'):rep(32),('a'):rep(32),('b'):rep(32),('c'):rep(32)
local replica='X4AuthorityReplicaMotionBind';local saved='X4AuthoritySavedBaselineMotionBind'
local function rig(max)
 local handlers,requests,faults={},{},{};local permitted=true;local r
 r=assert(M.new({enabled=true,max_generations=max or 4,max_tracks=2,
  register=function(name,cb)assert(not handlers[name]);handlers[name]=cb;return true end,
  send=function(screen,op,args)requests[#requests+1]={screen,op,args.request_id};return true end,
  guard=function()return permitted end,retire_guard=function()return permitted end,
  fault=function(reason)faults[#faults+1]=reason end}))
 assert(r:start());return r,handlers,requests,faults,function(v)permitted=v end
end
local function owner()
 local o={phase='ready',calls=0}
 function o:state()return self.phase end
 function o:event(_,route)assert(route=='saved' or route=='replica');self.calls=self.calls+1;self.phase='ready';return true end
 return o
end
local function args(nonce,index,seq,baseline)
 return {request_id=nonce..'-'..index..'-'..seq,index=index,epoch=e,sector_macro='sector_a',baseline=baseline}
end
local function event(handlers,route,id)
 handlers['X4Authority'..(route=='saved' and 'SavedBaseline' or 'Replica')..'MotionBind.Result'](nil,id..'|Unavailable|')
end
local r,h,_,f=rig();local a,b=owner(),owner();assert(r:attach(g1,n1,e,a))
local first=args(n1,42,1,100);assert(r:issue(saved,'Bind',first));event(h,'saved',first.request_id);assert(a.calls==1)
a.phase='stopped';assert(r:retire());assert(r:attach(g2,n2,e,b))
local next=args(n2,42,1,100);assert(r:issue(saved,'Bind',next));event(h,'saved',next.request_id);assert(b.calls==1)
-- Old generations never route to the new owner.
r,h,_,f=rig();a,b=owner(),owner();assert(r:attach(g1,n1,e,a));a.phase='stopped';assert(r:retire());assert(r:attach(g2,n2,e,b))
next=args(n2,42,1,100);assert(r:issue(saved,'Bind',next));event(h,'saved',first.request_id);assert(r:state()=='failed' and b.calls==0 and #f==1)
-- No uncorrelated, duplicate or wrong-screen reply is accepted.
for _,kind in ipairs({'unknown','wrong_route','duplicate'})do
 r,h,_,f=rig();a=owner();assert(r:attach(g1,n1,e,a));first=args(n1,42,1,100);assert(r:issue(saved,'Bind',first))
 if kind=='wrong_route' then event(h,'replica',first.request_id)
 elseif kind=='unknown' then event(h,'saved',n1..'-43-1')
 else event(h,'saved',first.request_id);event(h,'saved',first.request_id) end
 assert(r:state()=='failed' and #f==1)
end
-- A stopped owner and outer STOP confirmation are required, without pending MD.
r,h=rig();a=owner();assert(r:attach(g1,n1,e,a));assert(not r:retire() and r:state()=='failed')
r,h=rig();a=owner();assert(r:attach(g1,n1,e,a));first=args(n1,42,1,100);assert(r:issue(saved,'Bind',first));a.phase='stopped';assert(not r:retire())
r,h,_,_,allow=rig();a=owner();assert(r:attach(g1,n1,e,a));a.phase='stopped';allow(false);assert(not r:retire())
-- Sealed identifiers and bounded generations/tracks cannot be reused/evicted.
r=rig(1);a=owner();assert(r:attach(g1,n1,e,a));a.phase='stopped';assert(r:retire());assert(not r:attach(g2,n2,e,owner()))
r=rig();a=owner();assert(r:attach(g1,n1,e,a));a.phase='stopped';assert(r:retire());assert(not r:attach(g2,n1,e,owner()))
r,h=rig();a=owner();assert(r:attach(g1,n1,e,a));first=args(n1,42,1,100);assert(r:issue(saved,'Bind',first));event(h,'saved',first.request_id);assert(not r:issue(saved,'Bind',first))
r,h=rig();a=owner();assert(r:attach(g1,n1,e,a));first=args(n1,42,1,100);assert(r:issue(saved,'Bind',first));a.event=function()return true end;event(h,'saved',first.request_id);assert(r:state()=='failed')
r,h=rig();a=owner();assert(r:attach(g1,n1,e,a));for i=1,2 do local x=args(n1,i,1,100);assert(r:issue(saved,'Bind',x));event(h,'saved',x.request_id)end;assert(not r:issue(saved,'Bind',args(n1,3,1,100)))
-- A foreign callback during issue faults even when send swallows its failure.
local handlers={};local reentrant
reentrant=assert(M.new({enabled=true,max_generations=2,max_tracks=2,register=function(n,cb)handlers[n]=cb;return true end,
 guard=function()return true end,retire_guard=function()return true end,fault=function()end,
 send=function(_,_,v)handlers['X4AuthoritySavedBaselineMotionBind.Result'](nil,v.request_id..'|Unavailable|');return true end}))
assert(reentrant:start() and reentrant:attach(g1,n1,e,owner()));assert(not reentrant:issue(saved,'Bind',args(n1,42,1,100)) and reentrant:state()=='failed')
-- Router reentrancy from the recipient and from the STOP-confirmation fence
-- cannot be swallowed and turned into a successful transition.
r,h=rig();a=owner();function a:event()r:event('saved',first.request_id..'|Unavailable|');return true end
assert(r:attach(g1,n1,e,a));first=args(n1,42,1,100);assert(r:issue(saved,'Bind',first))
event(h,'saved',first.request_id);assert(r:state()=='failed')
local self_ref
self_ref=assert(M.new({enabled=true,max_generations=2,max_tracks=2,register=function()return true end,send=function()return true end,
 guard=function()return true end,fault=function()end,retire_guard=function()self_ref:attach(g2,n2,e,owner());return true end}))
assert(self_ref:start());a=owner();assert(self_ref:attach(g1,n1,e,a));a.phase='stopped';assert(not self_ref:retire() and self_ref:state()=='failed')
-- Replacing configuration after construction cannot replace guards or limits.
local enabled=true
local mutable={enabled=true,max_generations=1,max_tracks=1,register=function()return true end,send=function()return true end,
 guard=function()return enabled end,retire_guard=function()return true end,fault=function()end}
local fixed=assert(M.new(mutable));mutable.guard=function()return true end;mutable.max_generations=100
assert(fixed:start());enabled=false;assert(not fixed:attach(g1,n1,e,owner()) and fixed:state()=='failed')
mutable.max_generations=1;fixed=assert(M.new(mutable));mutable.max_generations=100
assert(fixed:start());a=owner();assert(fixed:attach(g1,n1,e,a));a.phase='stopped';assert(fixed:retire());assert(not fixed:attach(g2,n2,e,owner()))
-- Native registration ownership is claimed once, including partial failure.
local native=dofile('src/authority/lua/client_motion_event_router.lua');local native_handlers={}
function RegisterEvent(name,fn)assert(not native_handlers[name]);native_handlers[name]=fn end
function AddUITriggeredEvent()end
local options={enabled=true,max_generations=2,max_tracks=2,guard=function()return true end,
 retire_guard=function()return true end,fault=function()end}
local one=assert(native.new_x4(options));assert(native_handlers['X4AuthorityReplicaMotionBind.Result']==nil and one:start())
assert(not pcall(native.new_x4,options))
local partial=dofile('src/authority/lua/client_motion_event_router.lua');native_handlers={};local registration_count=0
function RegisterEvent(name,fn)
 registration_count=registration_count+1
 if registration_count==2 then return false end
 native_handlers[name]=fn
end
one=assert(partial.new_x4(options));assert(not one:start() and one:state()=='failed')
assert(type(native_handlers['X4AuthorityReplicaMotionBind.Result'])=='function' and not pcall(partial.new_x4,options))
print('client motion router checks passed')
