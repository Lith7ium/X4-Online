-- The same UI owner routes saved-baseline and new-replica events separately.
local core=dofile('src/authority/lua/motion_client_owner.lua')
local function rig(mode)
 local input,out,callbacks={}, {}, {};local routes={};local now=1;local allowed=true;local healthy=true;local flip=false;local pushes=0
 local sock={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
 local function factory(route)
  return function(opt)
   routes[#routes+1]={route=route,index=opt.index}
   return {begin=function()return true end,tick=function()return true end,event=function(_,value)
    assert(value=='ok');return opt.complete({epoch=opt.epoch,generation=opt.generation,index=opt.index,sequence=1,sector_macro=opt.sector_macro,
     evidence=route=='saved' and 'local_saved_registry' or nil,checkpoint_identity_proven=false,cross_process_identity_proven=false})
   end}
  end
 end
 local saved={enabled=true,baseline=100,guard=function(epoch,b)
  assert(epoch==('c'):rep(32) and b==100);if flip then healthy=false end;return allowed
 end,register=function(cb)callbacks.saved=cb;return true end,factory=factory('saved')}
 local owner=assert(core.new({enabled=true,lease=('a'):rep(32),attempt=('b'):rep(32),epoch=('c'):rep(32),generation=('d'):rep(32),nonce=('e'):rep(32),
  timeout=2,max_age=2,max_tracks=10,clock=function()return now end,guard=function()return healthy end,net=sock,fault=function()end,
  register=function(cb)callbacks.replica=cb;return true end,factory=factory('replica'),saved_baseline=saved,
  buffer={new=function()return {push=function()pushes=pushes+1;return true end}end}}))
 assert(owner:start());saved.baseline=1;saved.guard=function()return false end -- frozen config
 local function request(index,route)
  input[1]=table.concat({'M',('a'):rep(32),('b'):rep(32),'BIND',('f'):rep(32),('c'):rep(32),('d'):rep(32),tostring(index),'1','sector_a',('1'):rep(64),'10','1','2','3','-','-','-'},'|')
  assert(owner:tick());assert(#out==1+pushes)
  if mode=='guard' then allowed=false end
  if mode=='guard_invalidates' then flip=true end
  callbacks[route](nil,'ok')
 end
 if mode=='normal' then
  request(42,'saved');assert(owner:state()=='ready' and routes[1].route=='saved' and pushes==1 and #out==2)
  request(101,'replica');assert(owner:state()=='ready' and routes[2].route=='replica' and pushes==2 and #out==3)
 else
  request(42,mode=='wrong_route' and 'replica' or 'saved')
  assert(owner:state()=='failed' and pushes==0 and #out==1)
 end
end
for _,mode in ipairs({'normal','wrong_route','guard','guard_invalidates'})do rig(mode)end
print('separate saved baseline routing checks passed')
