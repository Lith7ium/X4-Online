-- Actual net.c pending() behavior on empty, oversized and ordinary UDP.
local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local lib=assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')),'luaopen_x4lan_net'))()
local sock=assert(lib.open('127.0.0.1',assert(tonumber(os.getenv('TEST_NET_PORT')))))
assert(sock:pending()==false and sock:send('READY'))
for i=1,3 do
 local loops=0
 while sock:pending()==false do ffi.C.usleep(1000);loops=loops+1;assert(loops<3000)end
 assert(sock:pending()==true)
 local data=sock:receive()
 if i<3 then assert(data==nil)else assert(data=='late')end
 io.stdout:write('GOT '..i..'\n');io.stdout:flush()
end
assert(sock:pending()==false);sock:close();assert(sock:pending()==nil)
