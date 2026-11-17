-- Synthetic ABI and events, not an X4 run.
local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local events,requests,logs={},{},{}
local clock=1
function RegisterEvent(name,fn) assert(not events[name]);events[name]=fn end
function DebugError(value) logs[#logs+1]=value end
function AddUITriggeredEvent(screen,op,args) requests[#requests+1]={screen,op,args} end
function GetCurRealTime() return clock end
X4LAN_CONFIG={authority_player_fixture_save=true,authority_sector_epoch=epoch,
 authority_player_fixture_nonce=nonce,authority_player_fixture_timeout=120,authority_read_save_path='/tmp/45841/save'}
dofile('tools/dev/authority_player_fixture_save_probe.lua')
local function send(name,value) assert(events[name]);events[name](nil,value) end
X4LAN_PLAYER_FIXTURE_SAVE_TICK();assert(requests[1][2]=='Preflight')
if arg[2]=='bad_preflight' then
 send('X4AuthorityPlayerSeatExperiment.Preflight','bad')
 assert(logs[#logs]:match(' ERROR$') and not pcall(X4LAN_PLAYER_FIXTURE_SAVE_TICK));return
end
send('X4AuthorityPlayerSeatExperiment.Preflight',nonce..'|'..epoch..'|ok')
X4LAN_PLAYER_FIXTURE_SAVE_TICK();assert(requests[2][2]=='Create')
send('X4AuthorityPlayerSectorFixture.Created',2)
assert(X4LAN_PLAYER_FIXTURE_SAVE_READY());X4LAN_PLAYER_FIXTURE_SAVE_TICK()
assert(logs[1]:match(' PREFLIGHT$') and logs[2]:match(' CREATED$'))
if arg[2]=='timeout' then clock=122;assert(not pcall(X4LAN_PLAYER_FIXTURE_SAVE_TICK))
else
 send('X4AuthorityPlayerSectorFixture.Created',2)
 assert(not X4LAN_PLAYER_FIXTURE_SAVE_READY() and not pcall(X4LAN_PLAYER_FIXTURE_SAVE_TICK))
end
