local mod=dofile('src/authority/lua/source_motion_ipc.lua')
local lease,attempt,epoch,gen=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32)
local function rig()
 local input,out={},{};local now=1;local fault
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end,pending=function()return #input>0 end}
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
-- V2 preserves NAV2's complete pose and Euler-coordinate rates. Missing one
-- half of the paired rate is never sent as a successful sample.
do
 local x,input,out=rig();bind(x,input,out)
 input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick())
 assert(x:complete({version=2,epoch=epoch,generation=gen,index=2,sequence=1,sector_macro='sector_a',source_time=42,
  x=1,y=2,z=3,orientation={yaw=1,pitch=2,roll=3},velocity={x=4,y=5,z=6},angular_rate={yaw=1,pitch=2,roll=3}}))
 assert(out[#out]=='S|'..lease..'|'..attempt..'|SAMPLE2'..suffix..'|1|2|1|sector_a|42|1|2|3|1|2|3|4|5|6|1|2|3')
end
do
 local x,input,out=rig();bind(x,input,out)
 input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick())
 assert(not x:complete({version=2,epoch=epoch,generation=gen,index=2,sequence=1,sector_macro='sector_a',source_time=42,
  x=1,y=2,z=3,orientation={yaw=1,pitch=2,roll=3},velocity={x=4,y=5,z=6}}))
 assert(x:state()=='failed' and #out==2)
end
-- V3 preserves real-clock rates, including unknown and measured zero.
local function v3()return {version=3,epoch=epoch,generation=gen,index=2,sequence=1,sector_macro='sector_a',source_time=42,capture_time=8,x=1,y=2,z=3}end
for _,case in ipairs({{nil,'-|-|-'},{{x=0,y=0,z=0},'0|0|0'},{{x=1,y=-2,z=3},'1|-2|3'}})do
 local x,input,out=rig();bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick())
 local sample=v3();sample.real_velocity=case[1];assert(x:complete(sample))
 assert(out[#out]=='S|'..lease..'|'..attempt..'|SAMPLE3'..suffix..'|1|2|1|sector_a|42|8|1|2|3|'..case[2])
end
for _,alter in ipairs({
 function(v)v.capture_time=nil end,function(v)v.capture_time=0/0 end,function(v)v.capture_time=-1 end,
 function(v)v.velocity={x=0,y=0,z=0} end,function(v)v.extra=true end,
 function(v)v.real_velocity={x=0,y=0} end,function(v)v.real_velocity={x=0,y=0,z=0,extra=1} end,
 function(v)v.orientation={yaw=0,pitch=0,roll=0} end,
 function(v)v.version=1;v.velocity=nil;v.real_velocity={x=0,y=0,z=0} end})do
 local x,input,out=rig();bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick())
 local sample=v3();alter(sample);assert(not x:complete(sample) and x:state()=='failed' and #out==2)
end
do local x,input,out=rig();bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|2';assert(not x:tick())end
do local x,input,out,clock=rig();bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick());clock(6);assert(not x:tick())end
do local x,input,out=rig();bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick());input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|2';assert(not x:tick())end
assert(mod.new({enabled=false})==nil)
-- STOP is opt-in, correlated and cannot succeed while sampling or closure fails.
do
 local closed=0;local input,out={},{};local now=1;local fault
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end,pending=function()return #input>0 end}
 local x=assert(mod.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,timeout=5,
  clock=function()return now end,guard=function()return true end,net=net,fault=function(v)fault=v end,
  stop=function()closed=closed+1;return true end}))
 bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|STOP'..suffix..'|1'
 assert(x:tick() and x:state()=='stopped' and closed==1 and not fault)
 assert(out[#out]=='S|'..lease..'|'..attempt..'|STOPPED'..suffix..'|1')
 assert(not x:tick() and x:state()=='failed')
end
for _,mode in ipairs({'disabled','wrong_sequence','wrong_epoch','pending','callback_failure'})do
 local input,out={},{};local closed=0
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end,pending=function()return #input>0 end}
 local cfg={enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,timeout=5,
  clock=function()return 1 end,guard=function()return true end,net=net,fault=function()end}
 if mode~='disabled' then cfg.stop=function()closed=closed+1;return mode~='callback_failure' end end
 local x=assert(mod.new(cfg));bind(x,input,out)
 if mode=='pending' then input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(x:tick()) end
 local e=mode=='wrong_epoch' and string.rep('f',32) or epoch
 local request=mode=='wrong_sequence' and '2' or '1'
 input[1]='P|'..lease..'|'..attempt..'|STOP|'..e..'|'..gen..'|'..request
 assert(not x:tick() and x:state()=='failed')
 for _,packet in ipairs(out)do assert(not packet:find('|STOPPED|',1,true))end
 assert(closed==(mode=='callback_failure' and 1 or 0))
end

-- A packet queued behind STOP is not allowed to follow a successful STOPPED.
do
 local input,out={},{};local closed=0
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end,pending=function()return #input>0 end}
 local x=assert(mod.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,timeout=5,
  clock=function()return 1 end,guard=function()return true end,net=net,fault=function()end,
  stop=function()closed=closed+1;return true end}))
 bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|STOP'..suffix..'|1';input[2]=''
 assert(not x:tick() and x:state()=='failed' and closed==1)
 for _,v in ipairs(out)do assert(not v:find('|STOPPED|',1,true))end
end
-- Failed or ambiguous readiness inspection must not acknowledge shutdown.
for _,mode in ipairs({'nil','raise','queued'})do
 local input,out={},{}
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end,
  pending=function()if mode=='raise' then error('pending failed')end;if mode=='nil' then return nil end;return true end}
 local x=assert(mod.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,timeout=5,
  clock=function()return 1 end,guard=function()return true end,net=net,fault=function()end,stop=function()return true end}))
 bind(x,input,out);input[1]='P|'..lease..'|'..attempt..'|STOP'..suffix..'|1'
 assert(not x:tick() and x:state()=='failed')
 for _,v in ipairs(out)do assert(not v:find('|STOPPED|',1,true))end
end
