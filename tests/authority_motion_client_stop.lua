-- Stop contract with a simulated local network and event router; no X4.
local core=dofile('src/authority/lua/motion_client_owner.lua')
local a,b,e,g,n=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32),('e'):rep(32)
local function rig(mode)
 local q,out,cb,faults,closes={}, {},nil,{},0
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(q,1)end}
 local o=assert(core.new({enabled=true,lease=a,attempt=b,epoch=e,generation=g,nonce=n,timeout=2,max_age=2,max_tracks=1,
  clock=function()return 1 end,guard=function()return true end,net=net,fault=function(r)faults[#faults+1]=r end,
  stop=function()return mode~='refuse' end,register=function(fn)cb=fn;return true end,
  buffer={new=function()return {push=function()return true end}end},factory=function(opt)return {
   begin=function()return true end,tick=function()return true end,
   event=function()return opt.complete({epoch=e,generation=g,index=42,sequence=1,sector_macro='sector_a'})end,
   close=function()closes=closes+1;return true end}end}))
 assert(o:start());return o,q,out,function(v)cb(nil,v)end,faults,function()return closes end
end
local stop=table.concat({'M',a,b,'STOP',('f'):rep(32),e,g},'|')
local expected=table.concat({'R',a,b,'STOPPED',('f'):rep(32),e,g},'|')
local function bind(o,q,cb)
 q[1]=table.concat({'M',a,b,'BIND',('1'):rep(32),e,g,'42','1','sector_a',('2'):rep(64),'1','1','2','3','-','-','-'},'|')
 assert(o:tick());cb('response');assert(o:state()=='ready')
end
local o,q,out,cb,errors,closed=rig();bind(o,q,cb);q[1]=stop;assert(o:tick() and o:state()=='stopped')
assert(closed()==1 and out[#out]==expected and o:tick());cb('late')
assert(o:state()=='failed' and #errors==1)
o,q,out,cb,errors=rig();q[1]=stop;assert(o:tick());q[1]='late';assert(not o:tick() and o:state()=='failed' and #errors==1)
o,q,out=rig('refuse');q[1]=stop;assert(not o:tick() and o:state()=='failed' and out[#out]~=expected)
o,q,out=rig();q[1]=stop;q[2]='late';assert(not o:tick() and o:state()=='failed' and out[#out]~=expected)
o,q,out,cb=rig();q[1]=table.concat({'M',a,b,'BIND',('1'):rep(32),e,g,'42','1','sector_a',('2'):rep(64),'1','1','2','3','-','-','-'},'|');assert(o:tick());q[1]=stop;assert(not o:tick() and out[#out]~=expected)
do
 local pending,reactor,owner,failures=stop,nil,nil,0
 local socket={send=function()return true end,receive=function()
  if reactor then local f=reactor;reactor=nil;f() end
  local p=pending;pending=nil;return p
 end}
 owner=assert(core.new({enabled=true,lease=a,attempt=b,epoch=e,generation=g,nonce=n,timeout=2,max_age=2,max_tracks=1,
  clock=function()return 1 end,guard=function()return true end,net=socket,fault=function()failures=failures+1 end,
  stop=function()return true end,register=function()return true end,buffer={new=function()return {}end},factory=function()return {}end}))
 assert(owner:start() and owner:tick() and owner:state()=='stopped')
 reactor=function()owner:event('late')end
 assert(not owner:tick() and owner:state()=='failed' and failures==1)
end
print('client stop contract passed')
