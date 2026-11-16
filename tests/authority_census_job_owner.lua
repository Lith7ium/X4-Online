local M=dofile('tools/dev/authority_census_job_owner.lua');assert(M.new({})==nil)
local epoch,attempt,lease,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32)
local function rig(role,opt)
 opt=opt or {};local now,game,paused=1,30,true;local input,output,logs={},{},{};local app,report,fault;local actor={id='private'}
 local net={send=function(_,v)output[#output+1]=v;return true end,receive=function()return table.remove(input,1)end,close=function()end}
 local host={start=function()return true end,state=function()return 'waiting' end,tick=function()
  if opt.attach~=false then
   if not opt.started then opt.started=true;return true,'attached_wait_running' end
   if not opt.reported then opt.reported=true;assert(report({epoch=epoch,index=10055,sequence=2,classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false},actor)) end
  end
  return true,'waiting'
 end}
 local cfg={enabled=true,role=role,lease=lease,epoch=epoch,attempt=attempt,nonce=nonce,timeout=100,window=30,net=net,
  clock=function()return now end,observe=function()return paused,game end,guard=function()return not opt.bad_guard end,
  pause=function()paused=true end,resume=function()paused=false;game=31 end,baseline_request=function(e,n)assert(e==epoch and n==nonce);return true end,log=function(s)logs[#logs+1]=s end,
  host_factory=function(r,f)report,fault=r,f;return host end,
  descriptor_factory=function(r,a)assert(r.sequence==2 and r.index==10055 and a==actor);return {start=function()return true end,tick=function()return true end,close=function()if opt.descriptor_close_error then error('close') end;if opt.descriptor_close_reenter then app:fault() end;return true end,
   response=function(_,v)if opt.descriptor_error then error('response') end;if v~='ok' then return false end;return true,{epoch=epoch,index=10055,sequence=2,macro='ship_macro',owner='argon',sector_macro='sector_a',x=1,y=2,z=3}end} end,
  witness_factory=function(index,macro)return {start=function()return true end,tick=function()return true end,close=function()if opt.close_error then error('close') end;if opt.close_reenter then app:fault() end;return true end,
   response=function(_,v)if opt.witness_error then error('response') end;if v~='ok' then return false end;return true,{epoch=epoch,index=index,sector_macro=macro,local_witness_match=true}end}end}
 app=assert(M.new(cfg));local cmd=table.concat({'CMD',lease,role,attempt,epoch},'|')
 return app,input,output,logs,cmd,opt,function(v)now=v end,function()if fault then fault() end end
end
local source,si,so,sl,sp,opt=rig('server');assert(source:tick());assert(source:state()=='ready' and sl[1]=='READY')
si[1]=sp..'|START';assert(source:tick());assert(source:tick());assert(source:state()=='captured');assert(source:tick());assert(source:tick());assert(source:tick());assert(source:state()=='descriptor_wait')
assert(source:descriptor_event('ok'));assert(source:state()=='descriptor_pending');assert(source:tick());assert(source:state()=='descriptor_sent' and sl[#sl]=='DESCRIPTOR')
assert(so[#so]:match('|DESCRIPTOR|2|10055|ship_macro|argon|sector_a|1|2|3$'))
si[1]=sp..'|WITNESS|2|41|sector_a';assert(source:tick());assert(source:state()=='witness_wait');assert(source:witness_event('ok'));assert(source:tick());assert(sl[#sl]=='WITNESS_OK')
si[1]=sp..'|CHECK|1';assert(source:tick() and so[#so]:match('|CHECKED|1$'))
local client,ci,co,cl,cp=rig('client');assert(client:tick() and #cl==0);assert(client:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(client:tick() and cl[1]=='READY');ci[1]=cp..'|WITNESS|2|41|sector_a';assert(client:tick());assert(client:witness_event('ok'));assert(client:tick() and cl[#cl]=='WITNESS_OK')
ci[1]=cp..'|WITNESS|2|41|sector_a';assert(not client:tick() and cl[#cl]=='FAULT')
local bad,bi,bo,bl,bp=rig('client');assert(bad:tick());assert(bad:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(bad:tick());bi[1]=bp..'|WITNESS|1|10055|sector_a';assert(not bad:tick() and bl[#bl]=='FAULT')
local lost,li,lo,ll,lp=rig('client');assert(lost:tick());assert(lost:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(lost:tick());li[1]=lp..'|WITNESS|2|41|sector_a';assert(lost:tick());assert(not lost:witness_event('unavailable') and ll[#ll]=='FAULT')
local late,_,_,late_log,_,_,_,fault=rig('server');assert(late:tick());fault();assert(late:state()=='failed' and late_log[#late_log]=='FAULT')
local wrong=rig('client');assert(wrong:tick());assert(not wrong:baseline_event(nonce..'|'..epoch..'|10054|unavailable'));assert(wrong:state()=='failed')
local expired,ei,_,elog,ep,_,clock=rig('server');assert(expired:tick());ei[1]=ep..'|START';assert(expired:tick());clock(41);assert(not expired:tick() and expired:state()=='failed')
local dup,di,_,dl,dp=rig('client');assert(dup:tick());assert(dup:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(dup:tick());di[1]=dp..'|CHECK|1';assert(dup:tick());di[1]=dp..'|CHECK|1';assert(not dup:tick() and dl[#dl]=='FAULT')
local changed,chi,_,chl,chp=rig('client');assert(changed:tick());assert(changed:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(changed:tick());chi[1]=chp..'|WITNESS|2|41|sector_a';assert(changed:tick());assert(changed:witness_event('ok'));assert(changed:tick());assert(not changed:witness_event('ok') and chl[#chl]=='FAULT')
for _,v in ipairs({string.rep('e',32)..'|'..epoch..'|10054|ok',nonce..'|'..string.rep('e',32)..'|10054|ok',nonce..'|'..epoch..'|10053|ok'})do local x=rig('client');assert(x:tick());assert(not x:baseline_event(v) and x:state()=='failed')end
local duplicate,_,_,dup_log=rig('client');assert(duplicate:tick());assert(duplicate:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(duplicate:tick());assert(not duplicate:baseline_event(nonce..'|'..epoch..'|10054|ok') and dup_log[#dup_log]=='FAULT')
local missing,_,missing_out,_,_,_,setclock=rig('client');assert(missing:tick());setclock(101);assert(not missing:tick());assert(#missing_out==1 and missing_out[1]:match('|FAULT$'))
for _,kind in ipairs({'witness_error','close_error'})do local flags={[kind]=true};local x,xi,xo,xl,xp=rig('client',flags);assert(x:tick());assert(x:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(x:tick());xi[1]=xp..'|WITNESS|2|41|sector_a';assert(x:tick());assert(not x:witness_event('ok') and x:state()=='failed' and xl[#xl]=='FAULT');for _,label in ipairs(xl)do assert(label~='WITNESS_OK')end end
local re,rei,_,rel,rep=rig('client',{close_reenter=true});assert(re:tick());assert(re:baseline_event(nonce..'|'..epoch..'|10054|ok'));assert(re:tick());rei[1]=rep..'|WITNESS|2|41|sector_a';assert(re:tick());assert(not re:witness_event('ok') and re:state()=='failed' and rel[#rel]=='FAULT')
for _,kind in ipairs({'descriptor_error','descriptor_close_error','descriptor_close_reenter'})do local flags={[kind]=true};local x,xi,xo,xl,xp=rig('server',flags);assert(x:tick());xi[1]=xp..'|START';assert(x:tick());assert(x:tick());assert(x:tick());assert(x:tick());assert(x:tick() and x:state()=='descriptor_wait');assert(not x:descriptor_event('ok') and x:state()=='failed' and xl[#xl]=='FAULT');for _,label in ipairs(xl)do assert(label~='DESCRIPTOR')end end
print('census owner tests passed')
