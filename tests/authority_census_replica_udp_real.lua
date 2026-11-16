local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]];local net=assert(package.loadlib(arg[1],'luaopen_x4lan_net'))().open('127.0.0.1',tonumber(arg[2]))
local W=dofile('tools/dev/authority_census_replica_udp.lua');local lease,attempt,epoch=string.rep('a',32),string.rep('b',32),string.rep('c',32);local prefix=table.concat({'CENSUS',lease,'client',attempt,epoch},'|');local time=0
local bstate='new';local wrapper=assert(W.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,timeout=5,net=net,clock=function()return time end,guard=function()return true end,log=function()end,replica_log=function()end,
 base_factory=function(proxy,log)return {tick=function()
  if bstate=='new' then bstate='ready';assert(proxy:send(prefix..'|READY'));return true end
  local msg=proxy:receive();if msg and msg:match('|WITNESS|2|41|sector_a$')then assert(proxy:send(prefix..'|WITNESS_OK|2|41|sector_a'));log('WITNESS_OK')
  elseif msg and msg:match('|CHECK|1$') then assert(proxy:send(prefix..'|CHECKED|1')) end
  return true end,fault=function()return true end}end,
 replica_factory=function()return {start=function()return true end,tick=function()return true,'intent_ready'end,take_intent=function()return true,{attempt=attempt,epoch=epoch,transport_sequence=1,job_sequence=2,index=10055}end}end}))
for i=1,3000 do assert(wrapper:tick());ffi.C.usleep(1000);time=time+.001 end
assert(wrapper:state()=='finished');wrapper:close()
