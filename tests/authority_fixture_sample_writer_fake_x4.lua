-- Runs the real Lua writer and native UDP module with simulated X4 FFI/MD.
local native_ffi = require('ffi')
native_ffi.cdef('int usleep(unsigned int);')
local lib = assert(package.loadlib(os.getenv('TEST_NET_LIB'), 'luaopen_x4lan_net'))()
local net = assert(lib.open('127.0.0.1', tonumber(os.getenv('TEST_NET_PORT'))))
local events, pending_event = {}, nil
local position = {x=100,y=20,z=30,yaw=.1,pitch=.2,roll=.3}
local C = {}
function C.GetSaveFolderPath() return '/tmp/private/45841/save' end
function C.IsPlayerValid() return true end
function C.IsGamePaused() return false end
function C.IsValidComponent(id) return id~=0 end
function C.IsComponentOperational() return true end
function C.IsComponentClass(id, class) return (id==101 and class=='ship') or (id==102 and class=='sector') or (id==103 and class=='zone') end
function C.GetContextByClass(id, class)
 if id==101 and class=='sector' then return 102 end
 if id==101 and class=='zone' then return 103 end
 if id==104 and class=='station' then return 104 end
 return 0
end
function C.GetPlayerControlledShipID() return 0 end
function C.GetPlayerOccupiedShipID() return 0 end
function C.GetPlayerContainerID() return 104 end
function C.GetObjectPositionInSector() return position end
function C.SetObjectSectorPos(actor, sector, target)
 assert(actor==101 and sector==102)
 position = {x=target.x,y=target.y,z=target.z,yaw=.1,pitch=.2,roll=.3}
end
package.loaded.ffi={C=C, NULL={}, typeof=function() return true end, cdef=function() end,
 string=function(value) return value end, new=function(_, value) return value end}
X4LAN_RESOLVE_STRING={parse_hex=function(value) return tonumber(value) end, actor_u64=function(value) return value~=0 and value or nil end}
X4LAN_AUTHORITY_MARKER_READY=function() return true end
ConvertStringToLuaID=function(value) return tonumber(value) end
ConvertIDTo64Bit=function(value) return value end
GetCurRealTime=function() return lib.monotonic() end
GetComponentData=function(id, field)
 if field=='isdocked' then return false,false,false end
 if field=='macro' and id==101 then return 'ship_arg_s_fighter_01_a_macro','player' end
 if field=='macro' and id==102 then return 'cluster_33_sector001_macro' end
 error('unexpected field')
end
RegisterEvent=function(name, callback) events[name]=callback;return true end
AddUITriggeredEvent=function(_,_,payload)
 assert(pending_event==nil)
 pending_event=payload.request_id
 return true
end
local module=dofile('tools/dev/authority_fixture_player_sample_writer.lua')
local owner=assert(module.new({enabled=true,epoch=string.rep('a',32),generation=string.rep('b',32),
 nonce=string.rep('c',32),lease=string.rep('d',32),attempt=string.rep('e',32),slot=1,net=net,
 expected_save_path='/tmp/private/45841/save',timeout=10,guard=function() return true end,log=function() return true end}))
local deadline=lib.monotonic()+15
while lib.monotonic()<deadline do
 assert(owner:tick())
 if pending_event then
  local request=pending_event;pending_event=nil
  events['X4AuthorityFixtureLocalOffset.Result'](nil,request..'|'..string.rep('a',32)..'|3|0x65|0x66|0x67')
 end
 native_ffi.C.usleep(1000)
end
