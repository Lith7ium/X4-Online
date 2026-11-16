-- Real UDP protocol peer; fake owner only, no X4 or game APIs.
local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local net=assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')),'luaopen_x4lan_net'))()
local sock=assert(net.open('127.0.0.1',assert(tonumber(os.getenv('TEST_NET_PORT')))))
local m=dofile('src/authority/lua/source_motion_ipc.lua');local now=0;local closed=0
local app=assert(m.new({enabled=true,lease=string.rep('1',32),attempt=string.rep('2',32),
 epoch=string.rep('b',32),generation=string.rep('c',32),timeout=5,
 clock=function()return now end,guard=function()return true end,net=sock,
 fault=function(reason)io.stderr:write('FAIL '..reason..'\n')end,
 stop=function()closed=closed+1;return closed==1 end}))
assert(app:start())
while app:state()~='stopped' do
 assert(app:tick());ffi.C.usleep(1000);now=now+.001;assert(now<5)
end
assert(closed==1);io.stdout:write('STOPPED\n');io.stdout:flush()
-- Retain the socket for PID/port validation until the test-owned process stops.
while true do ffi.C.usleep(10000)end
