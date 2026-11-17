-- Real sector reader and recovered client owner with independent fake clients.
local mode=assert(arg[1])
local motion=dofile('tools/dev/authority_recovered_client_motion.lua')
local sector=dofile('src/authority/lua/player_sector_interest.lua')
local epoch=('a'):rep(32)
if mode=='factory_failure' or mode=='register_failure' then
 local output,callback={},nil
 local net={send=function(_,value)output[#output+1]=value;return true end}
 local configured={enabled=true,epoch=epoch,nonce=('d'):rep(32),router_generation=('e'):rep(32),
  guard=function()return true end,running=function()return true end,fault=function()end,
  router_factory=function()return {start=function()return true end,attach=function()return true end,state=function()return 'active' end}end,
  owner_factory=function()return {start=function()return net:send('READY')end,state=function()return 'ready' end,tick=function()return true end}end,
  player_sector={incarnation=('1'):rep(32),nonce=('2'):rep(32),
   factory=function()
    if mode=='factory_failure' then error('synthetic factory failure')end
    return {begin=function()return true end,event=function()return true end,tick=function()return true end,
     state=function()return 'idle' end,close=function()return true end}
   end,
   register=function(fn)callback=fn;return false end,report=function()return true end}}
 assert(not pcall(motion.new,configured) and #output==0)
 if callback then assert(not callback('late') and #output==0)end
 return
end
local function client(incarnation,nonce,macro)
 local instance={running=true,valid=true,requests={},reports={},faults={}}
 local callback,stop,owner
 local config={enabled=true,epoch=epoch,nonce=('d'):rep(32),router_generation=('e'):rep(32),
  guard=function()
   if instance.guard_reenter then
    instance.guard_reenter=false
    local request=assert(instance.requests[1])
    callback(request.request_id..'|'..epoch..'|'..incarnation..'|ok|0x2a|'..macro)
   end
   return instance.valid
  end,running=function()return instance.running end,
  fault=function(reason)instance.faults[#instance.faults+1]=reason end,
  router_factory=function()return {start=function()return true end,attach=function()return true end,state=function()return 'active' end}end,
  owner_factory=function(options)
   stop=options.stop
   owner={phase='ready',stop_requested=false,start=function()return true end,state=function(self)return self.phase end,
    tick=function(self)
     if self.stop_requested then if not stop()then return false end;self.phase='stopped' end
     return true
    end}
   return owner
  end,
  player_sector={incarnation=incarnation,nonce=nonce,
   factory=function(options)
    options.enabled=true;options.timeout=2;options.clock=function()return 1 end
    options.issue=function(_,_,args)instance.requests[#instance.requests+1]=args;return true end
    options.inspect=function(_,seen)if seen~=macro then return nil end;return '42' end
    return sector.new(options)
   end,
   register=function(fn)assert(not callback);callback=fn;return true end,
   report=function(value)
    instance.reports[#instance.reports+1]=value
    if mode=='mutate' then value.sector_macro='changed' end
    if mode=='reenter' then instance.owner:tick() end
    return true
   end}}
 instance.owner=assert(motion.new(config))
 function instance:answer()
  local request=assert(self.requests[1])
  return callback(request.request_id..'|'..epoch..'|'..incarnation..'|ok|0x2a|'..macro)
 end
 function instance:deliver(value)return callback(value)end
 function instance:stop()owner.stop_requested=true;return self.owner:tick()end
 return instance
end
local a=client(('1'):rep(32),('2'):rep(32),'sector_a')
local b=client(('3'):rep(32),('4'):rep(32),'sector_b')
assert(a.owner:tick() and b.owner:tick() and #a.requests==1 and #b.requests==1)
assert(a.requests[1].request_id~=b.requests[1].request_id)
if mode=='cross' then
 local request=a.requests[1]
 assert(not b:deliver(request.request_id..'|'..epoch..'|'..request.incarnation..'|ok|0x2a|sector_b'))
 assert(#b.reports==0 and b.owner:state()=='failed')
 assert(a:answer() and #a.reports==1)
elseif mode=='pending_stop' then
 assert(not a:stop() and a.owner:state()=='failed' and #a.reports==0)
 assert(b:answer() and b:stop())
elseif mode=='guard' then
 a.valid=false;assert(not a:answer() and #a.reports==0 and a.owner:state()=='failed')
 assert(b:answer() and b:stop())
elseif mode=='guard_reenter' then
 a.guard_reenter=true
 assert(not a:answer() and #a.reports==0 and a.owner:state()=='failed')
 assert(b:answer() and b:stop())
elseif mode=='mutate' or mode=='reenter' then
 assert(not a:answer() and a.owner:state()=='failed')
else
 assert(a:answer() and b:answer() and #a.reports==1 and #b.reports==1)
 assert(a.reports[1].sector_macro=='sector_a' and b.reports[1].sector_macro=='sector_b')
 for _,result in ipairs({a.reports[1],b.reports[1]})do
  for key in pairs(result)do assert(key=='epoch' or key=='incarnation' or key=='sequence' or key=='sector_macro')end
 end
 assert(a:stop() and b:stop())
 if mode=='late' then assert(not a:answer() and a.owner:state()=='failed' and b.owner:state()=='stopped') end
end
if mode=='ok' then assert(#a.faults==0 and #b.faults==0)end
