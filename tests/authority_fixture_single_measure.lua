local factory=dofile('tools/dev/authority_fixture_single_measure.lua')
local lease=string.rep('a',32)
local nonce=string.rep('b',32)
local paused=true
local incoming,outgoing={},{}
local valid=true
local game_time=10
local unpauses=0
local faults=0
local callbacks={valid=function() return valid end,paused=function() return paused end,
 clock=function() return game_time end,receive=function() return table.remove(incoming,1) end,
 send=function(value) outgoing[#outgoing+1]=value;return true end,
 unpause=function() unpauses=unpauses+1 end,error=function() faults=faults+1 end}
local tick=factory.new(callbacks,lease)
assert(tick() and outgoing[1]=='READY|'..lease)
incoming[1]='RESUME|'..lease..'|'..nonce
assert(tick() and unpauses==1)
assert(tick() and #outgoing==1)
paused=false
assert(tick() and outgoing[2]=='RESUMED|'..lease..'|'..nonce..'|10')
game_time=11
incoming[1]='CLOCK|'..lease..'|'..nonce
assert(tick() and outgoing[3]=='CLOCK_RESULT|'..lease..'|'..nonce..'|11')
paused=true
incoming[1]='CLOCK|'..lease..'|'..nonce
assert(not tick() and faults==1 and not tick() and #outgoing==3)
-- Never dispatch an invalid request or dispatch twice after failure.
paused=true;incoming={'RESUME|'..lease..'|wrong'};outgoing={};unpauses=0
local invalid=factory.new(callbacks,lease)
assert(invalid());assert(not invalid() and unpauses==0 and not invalid())
-- Losing the fixture blocks resumption.
valid=false;local unavailable=factory.new(callbacks,lease)
assert(not unavailable() and unpauses==0)
print('single fixture measurement Lua state machine OK')
