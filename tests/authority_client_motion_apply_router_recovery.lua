-- Fixture selection is local and fixed; MD and all callbacks are simulated.
local module=dofile('src/authority/lua/client_motion_event_router.lua')
local epoch='4ba7be438ebb04ec5bb85fdb95b5a488'
local nonce,generation,operation=('a'):rep(32),('b'):rep(32),('c'):rep(32)
local screen,event='X4AuthoritySavedMotionApply','X4AuthoritySavedMotionApply.Result'
local fixture='recovery_enh_870'
local function rig(mode)
 local handlers,sends={},0
 local router=assert(module.new({enabled=true,saved_apply=true,saved_apply_fixture=fixture,max_apply_requests=2,
  max_generations=1,max_tracks=1,register=function(name,cb)handlers[name]=cb;return true end,
  send=function(_,_,args)sends=sends+1;if mode=='mutate_send' then args.fixture='other' end;return true end,
  guard=function()return true end,retire_guard=function()return true end,fault=function()end}))
 local owner={phase='new'}
 function owner:state()return self.phase end
 function owner:event()return true end
 function owner:apply_event()return true end
 assert(router:start())
 if mode=='epoch_attach' then
  assert(not router:attach(generation,nonce,('f'):rep(32),owner) and sends==0)
  return
 end
 assert(router:attach(generation,nonce,epoch,owner));owner.phase='applying'
 local function request(phase)
  return {request_id=nonce..'-'..operation..'-'..phase,epoch=epoch,index=1318,
   fixture=fixture,actor=41,sector=43,zone=45}
 end
 local pre=request('pre')
 if mode=='missing' then pre.fixture=nil end
 if mode=='other' then pre.fixture='other' end
 if mode=='index' then pre.index=687 end
 if mode=='epoch' then pre.epoch=('f'):rep(32) end
 if mode=='missing' or mode=='other' or mode=='index' or mode=='epoch' or mode=='mutate_send' then
  assert(not router:issue(screen,'Inspect',pre) and router:state()=='failed')
  return
 end
 assert(router:issue(screen,'Inspect',pre));handlers[event](nil,pre.request_id..'|ok')
 assert(router:state()=='active')
 local post=request('post')
 if mode=='post_missing' then post.fixture=nil end
 if mode=='post_other' then post.fixture='other' end
 if mode=='post_actor' then post.actor=99 end
 if mode=='post_missing' or mode=='post_other' or mode=='post_actor' then
  assert(not router:issue(screen,'Inspect',post) and router:state()=='failed')
 else
  assert(router:issue(screen,'Inspect',post));handlers[event](nil,post.request_id..'|ok')
  assert(router:state()=='active')
 end
end
assert(not pcall(module.new,{enabled=true,saved_apply=true,saved_apply_fixture='other',max_apply_requests=1,max_generations=1,max_tracks=1}))
for _,mode in ipairs({'success','epoch_attach','missing','other','index','epoch','mutate_send','post_missing','post_other','post_actor'})do rig(mode)end
print('recovery fixture routing fences passed')
