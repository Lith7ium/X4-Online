local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local netmod=assert(package.loadlib(arg[1],'luaopen_x4lan_net'))();local role=arg[3]
local lease=role=='server' and string.rep('a',32) or string.rep('d',32)
local attempt=string.rep('b',32);local epoch=string.rep('c',32);local stage='new';local t=0
local wire=dofile('tools/dev/authority_sector_pair_create_udp.lua')
local udp=assert(wire.new({enabled=true,role=role,lease=lease,attempt=attempt,epoch=epoch,sector='sector_one',timeout=5,
 net=netmod.open('127.0.0.1',tonumber(arg[2])),clock=function()return t end,pair_guard=function()return true end,log=function()end,
 owner_factory=function(desc,complete,fault)
  return {start=function()stage=role=='server' and 'source' or 'await_descriptor';return true end,
   accept_descriptor=function(_,v)assert(v.x==-399.125);stage='done';assert(complete({attempt=attempt,epoch=epoch,sequence=1,index=3}));return true end,
   confirm_ack=function()stage='done';return true end,
   update=function()
    if stage=='source' then stage='await_ack';assert(desc({attempt=attempt,epoch=epoch,sequence=1,index=3,macro='ship_arg_s_fighter_01_a_macro',sector='sector_one',owner='argon',seed=7183,x=-399.125,y=100000,z=500.25})) end
    return true,stage
   end}
 end}))
for _=1,5000 do assert(udp:tick());ffi.C.usleep(1000);t=t+.001 end
assert(udp:state()=='finished');udp:close()
