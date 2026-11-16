local M=dofile('tools/dev/authority_census_job_owner.lua');assert(M.new({})==nil)
local epoch,attempt,lease,nonce=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32)
local function rig(role,opt)
 opt=opt or {};local now,game,paused=1,30,true;local input,output,logs={},{},{};local app,report,fault,done,hold,acked;local hostphase='waiting';local actor={id='private'}
 local net={send=function(_,v)output[#output+1]=v;return true end,receive=function()return table.remove(input,1)end,close=function()end}
 local host={start=function()return true end,state=function()return hostphase end,tick=function()
  if opt.attach~=false then
   if not opt.started then opt.started=true;return true,'attached_wait_running' end
   if not opt.reported then opt.reported=true
    if opt.no_event then
     local n=opt.no_event=='empty' and 0 or 1
     if n==1 then assert(report({epoch=epoch,index=42,sequence=1,classification='previously_unobserved_existing_index',birth_confirmed=false,delivery_confirmed=false},actor)) end
     hostphase='done';assert(done({registry_mode='attached',baseline_count=10054,baseline_known_count=0,birth_confirmed=false,delivery_confirmed=false,coverage='unknown',observed=n,acknowledged=opt.bad_count and n+1 or n,classification=n==0 and 'inconclusive_no_events' or 'local_activations_observed'}));return true,'done'
    end
    assert(report({epoch=epoch,index=10055,sequence=2,classification='new_registry_entry',birth_confirmed=false,delivery_confirmed=false},actor))
    if opt.defer then hostphase='await_delivery' end
   end
  end
  return true,hostphase
 end,confirm_delivery=function(_,e,s,i)assert(opt.defer and hold() and e==epoch and s==2 and i==10055);hostphase='front';return true end}
 local cfg={enabled=true,role=role,lease=lease,epoch=epoch,attempt=attempt,nonce=nonce,timeout=100,window=30,net=net,
  clock=function()return now end,observe=function()return paused,game end,guard=function()return not opt.bad_guard end,
  pause=function()paused=true end,resume=function()paused=false;game=31 end,baseline_request=function(e,n)assert(e==epoch and n==nonce);return true end,log=function(s)logs[#logs+1]=s end,
  defer_ack=opt.defer,delivery=opt.defer and dofile('src/authority/lua/job_delivery.lua') or nil,
  delivery_peers=opt.two and {{id='client1',incarnation=string.rep('e',32)},{id='client2',incarnation=string.rep('f',32)}} or nil,
  host_factory=function(r,f,d,h,a)report,fault,done,hold,acked=r,f,d,h,a;return host end,
  descriptor_factory=function(r,a)assert(r.sequence==2 and r.index==10055 and a==actor);return {start=function()return true end,tick=function()return true end,close=function()if opt.descriptor_close_error then error('close') end;if opt.descriptor_close_reenter then app:fault() end;return true end,
   response=function(_,v)if opt.descriptor_error then error('response') end;if v~='ok' then return false end;return true,{epoch=epoch,index=10055,sequence=2,macro='ship_macro',owner='argon',sector_macro='sector_a',x=1,y=2,z=3}end} end,
  witness_factory=function(index,macro)return {start=function()return true end,tick=function()return true end,close=function()if opt.close_error then error('close') end;if opt.close_reenter then app:fault() end;return true end,
   response=function(_,v)if opt.witness_error then error('response') end;if v~='ok' then return false end;return true,{epoch=epoch,index=index,sector_macro=macro,local_witness_match=true}end}end}
 app=assert(M.new(cfg));local cmd=table.concat({'CMD',lease,role,attempt,epoch},'|')
 return app,input,output,logs,cmd,opt,function(v)now=v end,function()if fault then fault() end end,
  function()assert(hostphase=='front');hostphase='waiting';return acked(epoch,2,10055)end,function(v)game=v end
end
local function two_ready()
 local x,xi,xo,xl,xp,_,_,_,ack=rig('server',{defer=true,two=true})
 assert(x:tick());xi[1]=xp..'|START';assert(x:tick());assert(x:tick());assert(x:tick());assert(x:tick());assert(x:tick())
 assert(x:descriptor_event('ok'));assert(x:tick());xi[1]=xp..'|WITNESS|2|41|sector_a';assert(x:tick());assert(x:witness_event('ok'));assert(x:tick())
 return x,xi,xo,xl,xp,ack
end
do
 local x,xi,xo,xl,xp,ack=two_ready()
 local descriptions=0;for _,label in ipairs(xl)do if label=='DESCRIPTOR' then descriptions=descriptions+1 end end;assert(descriptions==1)
 xi[1]=xp..'|DELIVERY_ACK|2|10055|client1|'..string.rep('e',32)
 assert(x:tick() and x:state()=='finished' and xo[#xo]:match('|PARTIAL_ACKED|2|10055|client1$'))
 for _,label in ipairs(xl)do assert(label~='SOURCE_ACKED')end
 xi[1]=xp..'|DELIVERY_ACK|2|10055|client2|'..string.rep('f',32)
 assert(x:tick() and x:state()=='ack_wait');assert(ack());assert(x:tick() and x:state()=='source_acked')
 assert(xo[#xo]:match('|SOURCE_ACKED|2|10055$'))
end
for _,bad in ipairs({'|DELIVERY_ACK|2|10055|client2|'..string.rep('f',32),
 '|DELIVERY_ACK|2|10055|client1|'..string.rep('f',32),
 '|DELIVERY_ACK|3|10055|client1|'..string.rep('e',32),
 '|DELIVERY_ACK|2|10055'}) do
 local x,xi,_,xl,xp=two_ready();xi[1]=xp..bad;assert(not x:tick() and x:state()=='failed')
 for _,label in ipairs(xl)do assert(label~='SOURCE_ACKED')end
end
do
 local x,xi,_,xl,xp=two_ready();local ack='|DELIVERY_ACK|2|10055|client1|'..string.rep('e',32)
 xi[1]=xp..ack;assert(x:tick());xi[1]=xp..ack;assert(not x:tick() and x:state()=='failed')
 for _,label in ipairs(xl)do assert(label~='SOURCE_ACKED')end
end
do
 local x,xi,_,xl,xp=rig('server',{defer=true,no_event='existing'})
 assert(x:tick());xi[1]=xp..'|START';assert(x:tick());assert(not x:tick() and x:state()=='failed')
 for _,label in ipairs(xl) do assert(label~='SOURCE_ACKED') end
end
local function deferred_ready()
 local x,xi,xo,xl,xp,_,setclock,_,ack,setgame=rig('server',{defer=true})
 assert(x:tick());xi[1]=xp..'|START';assert(x:tick());assert(x:tick());assert(x:tick());assert(x:tick());assert(x:tick())
 assert(x:descriptor_event('ok'));assert(x:tick());xi[1]=xp..'|WITNESS|2|41|sector_a';assert(x:tick());assert(x:witness_event('ok'));assert(x:tick())
 return x,xi,xo,xl,xp,setclock,ack,setgame
end
for _,suffix in ipairs({'|DELIVERY_ACK|1|10055','|DELIVERY_ACK|2|10054','|DELIVERY_ACK|2|10055|extra'}) do
 local x,xi,_,xl,xp=deferred_ready();xi[1]=xp..suffix;assert(not x:tick() and x:state()=='failed')
 for _,label in ipairs(xl) do assert(label~='SOURCE_ACKED') end
end
do
 local x,xi,_,_,xp,_,_,setgame=deferred_ready();setgame(32);xi[1]=xp..'|DELIVERY_ACK|2|10055'
 assert(not x:tick() and x:state()=='failed')
end
do
 local x,xi,_,_,xp=deferred_ready();xi[1]=xp..'|DELIVERY_ACK|2|10055';assert(x:tick())
 xi[1]=xp..'|DELIVERY_ACK|2|10055';assert(not x:tick() and x:state()=='failed')
end
local source,si,so,sl,sp,opt=rig('server');assert(source:tick());assert(source:state()=='ready' and sl[1]=='READY')
si[1]=sp..'|START';assert(source:tick());assert(source:tick());assert(source:state()=='captured');assert(source:tick());assert(source:tick());assert(source:tick());assert(source:state()=='descriptor_wait')
assert(source:descriptor_event('ok'));assert(source:state()=='descriptor_pending');assert(source:tick());assert(source:state()=='descriptor_sent' and sl[#sl]=='DESCRIPTOR')
assert(so[#so]:match('|DESCRIPTOR|2|10055|ship_macro|argon|sector_a|1|2|3$'))
si[1]=sp..'|WITNESS|2|41|sector_a';assert(source:tick());assert(source:state()=='witness_wait');assert(source:witness_event('ok'));assert(source:tick());assert(sl[#sl]=='WITNESS_OK')
si[1]=sp..'|CHECK|1';assert(source:tick() and so[#so]:match('|CHECKED|1$'))
-- Deferred branch must retain the source head until the supervisor's
-- correlated client-delivery confirmation and a subsequent MD ACK receipt.
do
 local x,xi,xo,xl,xp,_,_,_,source_ack=rig('server',{defer=true})
 assert(x:tick());xi[1]=xp..'|START';assert(x:tick());assert(x:tick());assert(x:tick());assert(x:tick());assert(x:tick())
 assert(x:state()=='descriptor_wait' and x:descriptor_event('ok'));assert(x:tick() and x:state()=='descriptor_sent')
 xi[1]=xp..'|WITNESS|2|41|sector_a';assert(x:tick());assert(x:witness_event('ok'));assert(x:tick() and x:state()=='finished')
 xi[1]=xp..'|DELIVERY_ACK|2|10055';assert(x:tick() and x:state()=='ack_wait')
 for _,line in ipairs(xl) do assert(line~='SOURCE_ACKED') end
 assert(source_ack());assert(x:state()=='source_ack_pending');assert(x:tick() and x:state()=='source_acked')
 assert(xo[#xo]:match('|SOURCE_ACKED|2|10055$'))
end
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
for _,case in ipairs({'empty','existing'})do local n,ni,no,nl,np=rig('server',{no_event=case});assert(n:tick());ni[1]=np..'|START';assert(n:tick());assert(n:tick() and n:state()=='no_event_stop');assert(n:tick() and n:state()=='no_event_wait');assert(n:tick() and n:state()=='no_event_pending');assert(n:tick() and n:state()=='inconclusive' and nl[#nl]=='NO_EVENT' and no[#no]:match('|NO_EVENT$'));assert(n:tick());for _,v in ipairs(nl)do assert(v~='DESCRIPTOR' and v~='WITNESS_OK' and v~='FAULT')end end
local badsum,bsi,_,bsl,bsp=rig('server',{no_event='empty',bad_count=true});assert(badsum:tick());bsi[1]=bsp..'|START';assert(badsum:tick());assert(not badsum:tick() and bsl[#bsl]=='FAULT');for _,v in ipairs(bsl)do assert(v~='NO_EVENT')end
local faulted,fti,_,ftl,ftp,_,_,ftr=rig('server',{no_event='empty'});assert(faulted:tick());fti[1]=ftp..'|START';assert(faulted:tick());assert(faulted:tick() and faulted:state()=='no_event_stop');ftr();assert(faulted:state()=='failed' and ftl[#ftl]=='FAULT');for _,v in ipairs(ftl)do assert(v~='NO_EVENT')end
print('census owner tests passed')
