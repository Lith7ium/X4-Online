local core=dofile('src/authority/lua/job_client_owner.lua')
local client=dofile('tools/dev/authority_multi_create_client.lua')
local lease,attempt,epoch,generation,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32),string.rep('e',32)
local request,digest=string.rep('f',32),string.rep('1',64)
local function setup(inspect_failure,bad_witness)
 local t,healthy=1,true;local input,out,sent,faults={},{},{},{}
 local arms=0
 local net={send=function(_,p)out[#out+1]=p;return true end,receive=function()return table.remove(input,1)end}
 local owner=assert(core.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,nonce=nonce,
  baseline=2,seed=7183,timeout=5,client=client,net=net,clock=function()return t end,
  guard=function()return healthy end,witness=function(sector)assert(sector=='sector_a');if bad_witness then return nil end;return 1 end,
  fault=function(reason)faults[#faults+1]=reason end,
  issue=function(_,op,args)sent[#sent+1]={op=op,args=args};return true end,
  inspector={arm_running=function()arms=arms+1;return true end,
   inspect=function(_,a,s,i,d)assert(a=='0x29' and s=='0x2b' and i==3 and d.seed==7183);if inspect_failure then return nil,false,inspect_failure end;return '41',true end}}))
 local function req()return table.concat({'P',lease,attempt,'APPLY',request,epoch,generation,'1','3',digest,'ship_a','argon','sector_a','1','2','3'},'|')end
 local function ready()
  assert(owner:start());local a=sent[#sent].args
  assert(owner:event(a.request_id..'|Initialized|'..epoch));assert(owner:tick())
  assert(out[1]==table.concat({'X',lease,attempt,'READY',epoch,generation},'|'))
 end
 return owner,input,out,sent,faults,req,ready,function(v)t=v end,function(v)healthy=v end,function()return arms end
end
do
 local o,input,out,sent,errors,req,ready,_,_,arms=setup();ready();input[1]=req();assert(o:tick());assert(arms()==1 and #out==1)
 local a=sent[#sent];assert(a.op=='Create');assert(o:event(a.args.request_id..'|Created|3|0x29'));assert(#out==1)
 local b=sent[#sent];assert(b.op=='Inspect');assert(o:event(b.args.request_id..'|Inspected|3|0x29|0x2b'));assert(#out==1)
 assert(o:tick());assert(out[2]==table.concat({'X',lease,attempt,'APPLIED',request,epoch,generation,'1','3',digest},'|'))
 input[1]=req();assert(not o:tick() and o:state()=='failed' and #errors==1 and #out==2)
end
do local o,q,out,sent,errors,req,ready=setup();ready();q[1]=req():gsub(generation,string.rep('9',32));assert(not o:tick() and #out==1 and #errors==1)end
do local o,q,out,sent,errors,req,ready,settime=setup();ready();q[1]=req();assert(o:tick());settime(10);assert(not o:tick() and #out==1 and #errors==1)end
do local o,q,out,sent,errors,req,ready,_,health=setup();ready();q[1]=req();assert(o:tick());health(false);assert(not o:tick() and #out==1 and #errors==1)end
do local o,q,out,sent,errors,req,ready=setup();ready();q[1]=req();assert(o:tick());assert(not o:event('foreign') and #out==1 and #errors==1)end
do
 local o,q,out,sent,errors,req,ready=setup('position');ready();q[1]=req();assert(o:tick())
 local a=sent[#sent];assert(o:event(a.args.request_id..'|Created|3|0x29'))
 local b=sent[#sent];assert(not o:event(b.args.request_id..'|Inspected|3|0x29|0x2b'))
 assert(errors[1]=='event_inspector_position' and #out==1 and o:state()=='failed')
end
do
 local o,q,out,sent,errors,req,ready=setup('secret/path');ready();q[1]=req();assert(o:tick())
 local a=sent[#sent];assert(o:event(a.args.request_id..'|Created|3|0x29'))
 local b=sent[#sent];assert(not o:event(b.args.request_id..'|Inspected|3|0x29|0x2b'))
 assert(errors[1]=='event_actor_binding' and #out==1)
end
do
 local o,q,out,sent,errors,req,ready=setup(nil,true);ready();q[1]=req()
 assert(not o:tick() and errors[1]=='packet_witness' and #out==1 and o:state()=='failed')
end
assert(core.new({enabled=false})==nil)
