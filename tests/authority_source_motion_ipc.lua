local mod=dofile('src/authority/lua/source_motion_ipc.lua')
local lease,attempt,epoch,gen=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32)
local function rig()
 local input,out={},{};local now=1;local fault
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
 local app=assert(mod.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,timeout=5,
  clock=function()return now end,guard=function()return true end,net=net,fault=function(v)fault=v end}))
 return app,input,out,function(t)now=t end,function()return fault end
end
local suffix='|'..epoch..'|'..gen
local function bind(app,input,out)
 assert(app:start() and out[1]=='S|'..lease..'|'..attempt..'|HELLO'..suffix)
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(app:tick())
 assert(out[2]=='S|'..lease..'|'..attempt..'|ATTACHED'..suffix)
end
do
 local x,input,out=rig();bind(x,input,out)
 input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick() and x:requested())
 assert(x:complete(nil) and out[#out]=='S|'..lease..'|'..attempt..'|NO_SAMPLE'..suffix..'|1')
 input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|2';assert(x:tick())
 assert(x:complete({version=1,epoch=epoch,generation=gen,index=2,sequence=3,sector_macro='sector_a',source_time=42,x=1,y=2,z=3}))
 assert(out[#out]=='S|'..lease..'|'..attempt..'|SAMPLE'..suffix..'|2|2|3|sector_a|42|1|2|3|-|-|-')
 input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|3';assert(x:tick())
 assert(x:complete({version=1,epoch=epoch,generation=gen,index=2,sequence=4,sector_macro='sector_a',source_time=43,x=1,y=2,z=3,velocity={x=0,y=2,z=-3}}))
 assert(out[#out]:match('|0|2|%-3$'))
 input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|3';assert(not x:tick() and x:state()=='failed')
end
do local x,input,out=rig();bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|2';assert(not x:tick())end
do local x,input,out,clock=rig();bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick());clock(6);assert(not x:tick())end
do local x,input,out=rig();bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick());input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|2';assert(not x:tick())end
assert(mod.new({enabled=false})==nil)
