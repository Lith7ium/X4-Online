-- Synthetic driver contract only. No X4, no native bindings.
local mode=arg[1];local M=assert(loadfile('tools/dev/authority_sector_create_driver.lua'))()
if mode=='disabled' then assert(M.new({enabled=false})==nil);return end
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local q,records={},{};local count,now,game=10,1,3;local driver;local paused=true
local o={enabled=true,epoch=epoch,nonce=nonce,macros={'sector_a','sector_b'},
 clock=function()return now end,guard=function()
  if mode=='slow_guard' then now=now+6 end
  return mode~='guard' and paused,game
 end,count=function()
  if mode=='slow_count' then now=now+6 end
  return count
 end,
 issue=function(screen,op,args)
  if mode=='reentrant' and op=='Preflight' then driver:event('unexpected') end
  q[#q+1]={screen=screen,op=op,args=args}
  if mode=='slow_issue' and op=='Create' then now=now+6 end
  if mode=='pause_lost_issue' and op=='Create' then paused=false end
  return mode~='dispatch'
 end,
 snapshot=function(actor,sector)
  if mode=='slow_snapshot' then now=now+6 end
  if mode=='bad_snapshot' then return {actor_key='41',sector_key='43',x=0,y=100000,z=500} end
  return {actor_key=actor=='0x29' and '41' or '42',sector_key=sector=='0x2b' and '43' or '44',x=-400,y=100000,z=500}
 end,report=function(row)
  records[#records+1]=row
  if row.stage=='final' and row.index==4 then
   if mode=='slow_report' then now=now+6 end
   if mode=='pause_lost_report' then paused=false end
  end
  return mode~='report'
 end}
driver=assert(M.new(o))
local started=driver:start()
if not started then
 assert(driver:state()=='failed')
 if mode=='slow_guard' or mode=='slow_count' then assert(#q==0 and not driver:tick()) end
 return
end
for iteration=1,50 do
 now=now+.1
 local item=table.remove(q,1)
 if not item then break end
 local screen,op,args=item.screen,item.op,item.args
 if mode=='timeout' then now=now+6;assert(not driver:tick());break end
 if op=='Preflight' then driver:event(screen..'.Preflight',args.request_id..'|'..epoch..'|sector_a|sector_b')
 elseif op=='Initialize' then driver:event(screen..'.Initialized',epoch)
 elseif op=='Create' then
  if args.index==3 and count==10 then count=11 elseif args.index==4 and count==11 then count=12 end
  if mode=='bad_count' then count=count+1 end
  driver:event(screen..'.Created',mode=='wrong_index' and 9 or args.index)
 elseif op=='Inspect' then
  local id=args.index;local a=id==3 and '0x29' or '0x2a';local s=id==3 and '0x2b' or '0x2c'
  if mode=='bad_correlation' then args.request_id=nonce..'-999' end
  if mode=='changed' and #records>=1 and id==3 then a='0x2a' end
  local macro=id==3 and 'sector_a' or 'sector_b';local loc=id==3 and 'remote' or 'local'
  if mode=='no_remote' then loc='local' end
  local v=args.request_id..'|'..epoch..'|'..id..'|'..a..'|'..s..'|'..macro..'|'..loc
  driver:event(screen..'.Result',v)
  if mode=='duplicate' or (mode=='duplicate_final' and driver:state()=='done') then driver:event(screen..'.Result',v) end
 else error('unexpected request') end
 if driver:state()=='failed' or driver:state()=='done' then break end
end
if mode=='ok' then
 assert(driver:state()=='done' and #records==6 and records[1].index==3 and records[4].index==4 and records[6].stage=='final')
else
 assert(driver:state()=='failed',mode..' did not fail')
 if mode=='slow_issue' or mode=='pause_lost_issue' then assert(#q==1 and q[1].op=='Create');assert(not driver:tick());assert(#q==1) end
 if mode=='slow_report' or mode=='pause_lost_report' then assert(#records==6 and not driver:tick() and #q==0) end
end
print('sector create synthetic '..mode..' passed')
