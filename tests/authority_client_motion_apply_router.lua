-- Optional saved-position event routing; all callbacks and MD are simulated.
local module = dofile('src/authority/lua/client_motion_event_router.lua')
local epoch, nonce, generation = ('a'):rep(32), ('b'):rep(32), ('c'):rep(32)
local operation = ('d'):rep(32)
local screen = 'X4AuthoritySavedMotionApply'
local apply_event = 'X4AuthoritySavedMotionApply.Result'

local function rig(options)
 options = options or {}
 local handlers, failures, sent = {}, {}, {}
 local guard = true
 local router = assert(module.new({enabled=true, saved_apply=true, max_apply_requests=2,
  max_generations=2, max_tracks=2,
  register=function(name, callback)assert(not handlers[name]); handlers[name]=callback; return true end,
  send=function(name, kind, args)
   sent[#sent+1]={name=name,kind=kind,id=args.request_id}
   if options.reentrant then handlers[apply_event](nil,args.request_id..'|ok') end
   return true
  end,
  guard=function()return guard end, retire_guard=function()return guard end,
  fault=function(reason)failures[#failures+1]=reason end}))
 local owner={phase='new',calls=0}
 function owner:state()return self.phase end
 function owner:event()self.phase='ready';return true end
 function owner:apply_event(value)
  self.calls=self.calls+1
  if options.change_state then self.phase='ready' end
  if options.refuse_callback then return false end
  return true
 end
 assert(router:start() and router:supports_saved_apply())
 assert(router:attach(generation,nonce,epoch,owner))
 owner.phase='preflighting'
 return router, owner, handlers, failures, sent, function(value)guard=value end
end

local function request(token, phase, actor)
 return {request_id=nonce..'-'..token..'-'..phase,epoch=epoch,index=1318,
  actor=actor or 41,sector=43,zone=45}
end
local function deliver(handlers, args, status)
 handlers[apply_event](nil,args.request_id..'|'..(status or 'ok'))
end

-- Two independent preflights followed by a writer's pre and post inspection.
local router, owner, handlers = rig()
local first=request(operation,'pre')
assert(router:issue(screen,'Inspect',first));deliver(handlers,first)
assert(router:state()=='active' and owner.calls==1)
owner.phase='applying'
local write=request(('e'):rep(32),'pre')
assert(router:issue(screen,'Inspect',write));deliver(handlers,write)
local post=request(('e'):rep(32),'post')
assert(router:issue(screen,'Inspect',post));deliver(handlers,post)
assert(router:state()=='active' and owner.calls==3)
owner.phase='stopped';assert(router:retire())

-- Bind continues through its original route when apply routing is enabled.
router,owner,handlers=rig();owner.phase='pending'
local binding={request_id=nonce..'-1318-1',index=1318,epoch=epoch,
 sector_macro='cluster_115_sector001_macro',baseline=10054}
assert(router:issue('X4AuthoritySavedBaselineMotionBind','Bind',binding))
handlers['X4AuthoritySavedBaselineMotionBind.Result'](nil,binding.request_id..'|Bound|1318|0x29|0x2b')
assert(router:state()=='active' and owner.phase=='ready')

-- A retired generation's reply cannot satisfy a newer generation's request.
router,owner,handlers=rig();owner.phase='stopped';assert(router:retire())
local successor={phase='new',calls=0}
function successor:state()return self.phase end
function successor:event()return true end
function successor:apply_event()self.calls=self.calls+1;return true end
local next_nonce,next_generation=('1'):rep(32),('2'):rep(32)
assert(router:attach(next_generation,next_nonce,epoch,successor));successor.phase='preflighting'
local fresh=request(operation,'pre');fresh.request_id=next_nonce..'-'..operation..'-pre'
assert(router:issue(screen,'Inspect',fresh))
deliver(handlers,request(operation,'pre'))
assert(router:state()=='failed' and successor.calls==0)

-- Replayed or mismatched requests are fenced, even after completed delivery.
for _,kind in ipairs({'duplicate_pre','duplicate_post','unseen_post','different_actor','too_many',
                      'wrong_nonce','wrong_route','duplicate_event','old_event','refused','post_after_preflight','table_reference',
                      'changed_method','changed_state','guard_loss','reentrant','callback_failure'})do
 local options={reentrant=kind=='reentrant',refuse_callback=kind=='callback_failure'}
 router,owner,handlers,failures,sent,set_guard=rig(options)
 local a=request(operation,'pre')
 if kind=='table_reference' then
  a.actor={id=41};assert(not router:issue(screen,'Inspect',a))
 elseif kind=='wrong_nonce' then
  a.request_id=('f'):rep(32)..'-'..operation..'-pre'
  assert(not router:issue(screen,'Inspect',a))
 elseif kind=='unseen_post' then
  owner.phase='applying';assert(not router:issue(screen,'Inspect',request(operation,'post')))
 elseif kind=='reentrant' then assert(not router:issue(screen,'Inspect',a))
 else
  if kind=='duplicate_post' or kind=='different_actor' then owner.phase='applying' end
  assert(router:issue(screen,'Inspect',a))
  if kind=='wrong_route' then handlers['X4AuthorityReplicaMotionBind.Result'](nil,a.request_id..'|ok')
  elseif kind=='old_event' then handlers[apply_event](nil,('f'):rep(32)..'-'..operation..'-pre|ok')
  elseif kind=='refused' then deliver(handlers,a,'refused')
  elseif kind=='changed_method' then owner.apply_event=function()return true end;deliver(handlers,a)
  elseif kind=='changed_state' then owner.phase='applying';deliver(handlers,a)
  elseif kind=='guard_loss' then set_guard(false);deliver(handlers,a)
  elseif kind=='callback_failure' then deliver(handlers,a)
  else
   deliver(handlers,a)
   if kind=='post_after_preflight' then owner.phase='applying';assert(not router:issue(screen,'Inspect',request(operation,'post')))
   elseif kind=='duplicate_pre' then assert(not router:issue(screen,'Inspect',a))
   elseif kind=='duplicate_event' then deliver(handlers,a)
   elseif kind=='different_actor' then owner.phase='applying';assert(not router:issue(screen,'Inspect',request(operation,'post',99)))
   elseif kind=='too_many' then
    local b=request(('e'):rep(32),'pre');assert(router:issue(screen,'Inspect',b));deliver(handlers,b)
    assert(not router:issue(screen,'Inspect',request(('f'):rep(32),'pre')))
   elseif kind=='duplicate_post' then
    owner.phase='applying';local b=request(operation,'post');assert(router:issue(screen,'Inspect',b));deliver(handlers,b)
    assert(not router:issue(screen,'Inspect',b))
   end
  end
 end
 assert(router:state()=='failed' and #failures==1,kind)
end

-- The owner method is pinned through owns() and retirement too.
router,owner=rig();owner.apply_event=function()return true end
assert(not router:owns(generation,nonce,epoch,owner));owner.phase='stopped'
assert(not router:retire() and router:state()=='failed')
print('optional saved apply router checks passed')
