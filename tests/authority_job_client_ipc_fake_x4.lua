local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local netmod=assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')),'luaopen_x4lan_net'))()
local net=netmod.open('127.0.0.1',tonumber(assert(os.getenv('TEST_NET_PORT'))))
local core=dofile('src/authority/lua/job_client_owner.lua')
local client=dofile('tools/dev/authority_multi_create_client.lua')
local lease,attempt,epoch,gen=string.rep('a',32),string.rep('b',32),string.rep('c',32),string.rep('d',32)
local pending={};local owner;local start=netmod.monotonic();local inspect_due
owner=assert(core.new({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,nonce=string.rep('e',32),
 baseline=2,seed=7183,timeout=5,net=net,client=client,clock=netmod.monotonic,
 guard=function()return true end,witness=function(s)assert(s=='sector_a');return 1 end,
 fault=function(r)error(r)end,
 issue=function(_,op,args)pending[#pending+1]={op=op,args=args};if op=='Inspect' then inspect_due=netmod.monotonic()+.2 end;return true end,
 inspector={arm_running=function()return true end,inspect=function(_,a,s,i,d)
  assert(a=='0x29' and s=='0x2b' and i==3 and d.seed==7183);return '41',true end}}))
assert(owner:start())
while netmod.monotonic()-start<5 do
 if #pending>0 and (pending[1].op~='Inspect' or netmod.monotonic()>=inspect_due) then
  local q=table.remove(pending,1);local a=q.args
  local value=q.op=='Initialize' and a.request_id..'|Initialized|'..epoch or
   q.op=='Create' and a.request_id..'|Created|'..a.index..'|0x29' or
   a.request_id..'|Inspected|'..a.index..'|0x29|0x2b'
  assert(owner:event(value))
 end
 assert(owner:tick())
 ffi.C.usleep(1000)
end
