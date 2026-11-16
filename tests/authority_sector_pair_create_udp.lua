local M=dofile('tools/dev/authority_sector_pair_create_udp.lua')
assert(M.new({})==nil)
local now=1;local lease=string.rep('a',32);local attempt=string.rep('b',32);local epoch=string.rep('c',32)
local function new(role,flags)
 flags=flags or {};local inbox,outbox,logs={},{},{};local intents={};local stage='new'
 local net={send=function(_,v)if flags.send_fail then return false end;outbox[#outbox+1]=v;return true end,
  receive=function()return table.remove(inbox,1)end,close=function()return true end}
 local prefix=table.concat({'CMD',lease,role,attempt,epoch},'|')
 local udp=assert(M.new({enabled=true,role=role,lease=lease,attempt=attempt,epoch=epoch,sector='sector_one',timeout=10,net=net,
  clock=function()return now end,pair_guard=function()return not flags.guard_fail end,log=function(v)logs[#logs+1]=v end,
  owner_factory=function(desc,complete,fault)
   intents={desc=desc,complete=complete,fault=fault};flags.fault=fault
   return {start=function()stage=role=='server' and 'source' or 'await_descriptor';return true end,
    accept_descriptor=function(_,v)assert(v.x==-399.125 and v.sequence==1);stage='done';assert(complete({attempt=attempt,epoch=epoch,sequence=1,index=3}));if flags.drop_after_complete then flags.guard_fail=true end;return true end,
    confirm_ack=function()stage='done';return true end,
    update=function()
     if stage=='source' then stage='await_ack';assert(desc({attempt=attempt,epoch=epoch,sequence=1,index=3,macro='ship_arg_s_fighter_01_a_macro',sector='sector_one',owner='argon',seed=7183,x=-399.125,y=100000,z=500.25}));if flags.drop_after then flags.guard_fail=true end end
     return true,stage
    end}
  end}))
 return udp,inbox,outbox,logs,prefix,intents
end
local source,si,so,sl,sp=new('server');assert(source:tick());assert(#so==1 and sl[1]=='READY')
si[1]=sp..'|CHECK|1';assert(source:tick());assert(so[2]:match('|CHECKED|1$'))
si[1]=sp..'|START';assert(source:tick());assert(source:state()=='await_ack' and sl[3]=='DESCRIPTOR')
assert(so[3]:match('|DESCRIPTOR|1|3|ship_arg_s_fighter_01_a_macro|sector_one|argon|7183|%-399.125|100000|500.25$'))
si[1]=sp..'|ACK|1|3';assert(source:tick());assert(source:state()=='finished' and sl[4]=='FINISHED')
si[1]=sp..'|CHECK|2';assert(source:tick() and so[5]:match('|CHECKED|2$'))
si[1]=sp..'|ACK|1|3';assert(not source:tick() and source:state()=='failed' and sl[#sl]=='FAULT')
local client,ci,co,cl,cp=new('client');assert(client:tick());ci[1]=cp..'|START';assert(client:tick() and cl[2]=='AWAIT')
ci[1]=cp..'|DESCRIPTOR|1|3|ship_arg_s_fighter_01_a_macro|sector_one|argon|7183|-399.125|100000|500.25';assert(client:tick() and cl[3]=='INSPECTED')
for _,bad in ipairs({'CHECK|0','CHECK|01','CHECK|2147483648','DESCRIPTOR|1|3|bad','START|extra'}) do
 local t,i,o,l,p=new('client');assert(t:tick());i[1]=p..'|'..bad;assert(not t:tick() and l[#l]=='FAULT')
end
local t,i,o,l,p=new('client');assert(t:tick());i[1]=p..'|CHECK|1';assert(t:tick());i[1]=p..'|CHECK|1';assert(not t:tick())
local f,fi,fo,fl,fp=new('server',{drop_after=true});assert(f:tick());fi[1]=fp..'|START';assert(not f:tick());for _,v in ipairs(fl)do assert(v~='DESCRIPTOR')end
local x,xi,xo,xl,xp=new('client');assert(x:tick());xi[1]=xp:gsub(lease,string.rep('d',32))..'|START';assert(not x:tick() and xl[#xl]=='FAULT')
local slow,ui=new('client');assert(slow:tick());now=11;assert(not slow:tick());now=1
local cf={drop_after_complete=true};local cu,cui,cuo,cul,cup=new('client',cf);assert(cu:tick());cui[1]=cup..'|START';assert(cu:tick());cui[1]=cup..'|DESCRIPTOR|1|3|ship_arg_s_fighter_01_a_macro|sector_one|argon|7183|-399.125|100000|500.25';assert(not cu:tick());for _,v in ipairs(cul)do assert(v~='INSPECTED')end
local lf={};local late,latein,lateout,latelog,lateprefix=new('client',lf);assert(late:tick());assert(lf.fault);lf.fault();assert(late:state()=='failed' and latelog[#latelog]=='FAULT');assert(not late:tick())
local previous=package.loadlib;local closed=false;local fake_net={send=function()return true end,receive=function()return nil end,close=function()closed=true end};local created
package.loadlib=function(path,symbol)assert(path=='./extensions/x4_lan_lab/native/x4lan_net.so' and symbol=='luaopen_x4lan_net');return function()return {open=function(host,port)assert(host=='127.0.0.1' and port==3456);return fake_net end}end end
GetCurRealTime=function()return 1 end;DebugError=function()end
local real=assert(M.new_x4({enabled=true,role='server',port=3456,lease=lease,attempt=attempt,epoch=epoch,nonce=string.rep('e',32),sector='sector_one',timeout=300,pair_guard=function()return true end,expected_save_path='/tmp/45841/save',driver={},adapter={new=function(c)created=c;return {} end}}));assert(real:tick());assert(created.timeout==120 and created.role=='source');assert(real:close() and closed);package.loadlib=previous
print('udp fake checks passed')
