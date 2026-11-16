local core=dofile('src/authority/lua/motion_client_owner.lua')
local net={send=function()return true end,receive=function()return nil end}
local c={enabled=true,lease=('a'):rep(32),attempt=('b'):rep(32),epoch=('c'):rep(32),generation=('d'):rep(32),nonce=('e'):rep(32),
 timeout=1,max_age=1,max_tracks=10,clock=function()return 1 end,guard=function()return true end,
 buffer={new=function()return {push=function()return true end}end},register=function()return true end,factory=function()return {} end,fault=function()end,net=net}
local owner=assert(core.new(c));assert(not pcall(core.new,c))
assert(owner:start());assert(owner:tick())
print('exclusive motion IPC owner checks passed')
-- A defective injected buffer cannot mutate the sample and still receive BOUND.
for _,mode in ipairs({'value','pose_field','pose_meta','sample_field','sample_meta','rate_field','rate_meta'})do
 local q,out={},{};local cb
 local socket={send=function(_,s)out[#out+1]=s;return true end,receive=function()return table.remove(q,1)end}
 local x=assert(core.new({enabled=true,lease=('a'):rep(32),attempt=('b'):rep(32),epoch=('c'):rep(32),generation=('d'):rep(32),nonce=('e'):rep(32),
  timeout=2,max_age=2,max_tracks=10,clock=function()return 1 end,guard=function()return true end,net=socket,fault=function()end,
  register=function(f)cb=f;return true end,
  buffer={new=function()return {push=function(_,sample)
   if mode=='value' then sample.pose[1]=9
   elseif mode=='pose_field' then sample.pose.extra=9
   elseif mode=='pose_meta' then setmetatable(sample.pose,{})
   elseif mode=='sample_field' then sample.extra=9
   elseif mode=='sample_meta' then setmetatable(sample,{})
   elseif mode=='rate_field' then sample.rate.extra=9
   elseif mode=='rate_meta' then setmetatable(sample.rate,{}) end
   return true
  end}end},
  factory=function(opt)return {begin=function()return true end,tick=function()return true end,
   event=function()assert(opt.complete({epoch=opt.epoch,generation=opt.generation,index=opt.index,sequence=1,sector_macro=opt.sector_macro}));return true end}end}))
 assert(x:start());q[1]=table.concat({'M',('a'):rep(32),('b'):rep(32),'BIND',('f'):rep(32),('c'):rep(32),('d'):rep(32),'42','1','sector_a',('1'):rep(64),'10','1','2','3','4','5','6'},'|')
 assert(x:tick());cb(nil,'correlated');assert(x:state()=='failed' and #out==1)
end
