local module=dofile('src/authority/lua/client_authority_motion_session.lua')
local ipcmod=dofile('src/authority/lua/source_motion_ipc.lua')
local function rig(mode)
 local lease,attempt,epoch,generation=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32)
 local input,out={},{};local now=1;local granted=true;local callback,reader,session
 local net={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
 session=assert(module.new({enabled=true,epoch=epoch,generation=generation,index=1318,baseline=10054,
  guard=function()return true end,grant=function(e,g,i)
   assert(e==epoch and g==generation and i==1318)
   if mode=='reentrant' and session then pcall(function()session:tick()end)end
   return granted
  end,fault=function()end,audit=function()return mode~='audit_failure' end,register=function(f)callback=f;return true end,
  ipc_factory=function(x)return ipcmod.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
   timeout=5,clock=function()return now end,guard=x.guard,fault=x.fault,net=net,
   saved_baseline={limit=10054,guard=function()return x.guard()end}})end,
  reader_factory=function(x)
   local phase='new';local expected=('e'):rep(32);local pulls=0
   reader={start=function()phase='bootstrapping';return true end,state=function()return phase end,
    expected_request=function()return expected end,tick=function()
     if phase=='sampling' and not expected then
      pulls=pulls+1;if mode~='no_sample_then_sample' or pulls>1 then expected=('e'):rep(32) end
     end
     return true
    end,event=function(_,value)
     assert(value==expected..'|ok')
     if phase=='bootstrapping' then phase='sampling';expected=nil;return true end
     assert(x.stage_sample({version=1,epoch=epoch,generation=generation,index=1318,sequence=1,
      sector_macro='cluster_115_sector001_macro',source_time=10,x=1,y=2,z=3}))
     if mode=='late_failure' then return false end
     expected=nil;return true
    end}
   return reader
  end}))
 if mode=='reentrant' then assert(not session:start());return end
 assert(session:start() and out[1]=='S|'..lease..'|'..attempt..'|HELLO|'..epoch..'|'..generation)
 local suffix='|'..epoch..'|'..generation
 input[1]='P|'..lease..'|'..attempt..'|BOUND'..suffix;assert(session:tick())
 if mode=='pull_before_register' then
  input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|1';assert(not session:tick() and #out==2);return
 end
 input[1]='P|'..lease..'|'..attempt..'|REGISTER_SAVED'..suffix..(mode=='foreign_index' and '|1|1319|10054' or '|1|1318|10054')
 if mode=='foreign_index' then assert(not session:tick() and #out==2);return end
 assert(session:tick());assert(session:tick())
 assert(#out==2);callback(nil,('e'):rep(32)..'|ok');assert(session:tick() and out[3]:find('|SAVED_REGISTERED|',1,true))
 if mode=='grant_revoked' then granted=false;assert(not session:tick() and #out==3);return end
 input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|2';assert(session:tick())
 local expected_request=2
 if mode=='no_sample_then_sample' then
  assert(out[4]=='S|'..lease..'|'..attempt..'|NO_SAMPLE'..suffix..'|2')
  input[1]='P|'..lease..'|'..attempt..'|PULL'..suffix..'|3';assert(session:tick());expected_request=3
 else assert(#out==3)end
 callback(nil,('e'):rep(32)..'|ok')
 if mode=='late_failure' or mode=='audit_failure' then assert(session:state()=='failed' and #out==3);return end
 assert(out[#out]=='S|'..lease..'|'..attempt..'|SAMPLE'..suffix..'|'..expected_request..'|1318|1|cluster_115_sector001_macro|10|1|2|3|-|-|-')
end
for _,mode in ipairs({'ok','late_failure','grant_revoked','reentrant','pull_before_register','foreign_index','no_sample_then_sample','audit_failure'})do rig(mode)end
print('client authority local session IPC checks passed')
