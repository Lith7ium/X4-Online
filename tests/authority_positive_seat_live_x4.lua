local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
local epoch,nonce=string.rep('a',32),string.rep('b',32);local events,requests,logs={},{},{};local t=1
function RegisterEvent(n,f) assert(not events[n]);events[n]=f end
function DebugError(s)logs[#logs+1]=s end
function GetCurRealTime()return t end
function AddUITriggeredEvent(s,o,a)requests[#requests+1]={s,o,a}end
function ConvertStringToLuaID(s)local v=ffi.new('uint64_t',0);for d in s:gmatch('%d') do v=v*10+tonumber(d) end;return v end
function ConvertIDTo64Bit(v)return ffi.new('uint64_t',v)end
function GetComponentData(_,n)assert(n=='assignedpilot');if arg[2]=='getter_error' then error('private exception') end;return ffi.new('uint64_t',99)end
function X4LAN_SECTOR_READ_EXPORT()return ConvertStringToLuaID('9007199254740993'),ffi.new('uint64_t',11),2,3 end
X4LAN_CONFIG={authority_positive_seat_live=true,authority_positive_seat_timeout=20,authority_positive_seat_nonce=nonce,
 authority_sector_epoch=epoch,authority_read_save_path='/tmp/45841/save'}
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
dofile('tools/dev/authority_positive_seat_search.lua');dofile('tools/dev/authority_positive_seat_live_owner.lua')
X4LAN_POSITIVE_SEAT_LIVE_TICK();assert(#requests==1 and logs[#logs]:match(' START$'))
local mode=arg[2]
if mode=='timeout' then t=11;X4LAN_POSITIVE_SEAT_LIVE_TICK()
elseif mode=='inconclusive' then events['X4AuthorityPositiveSeatSearch.Inconclusive'](nil,nonce..'|'..epoch..'|inconclusive')
else events['X4AuthorityPositiveSeatSearch.Result'](nil,nonce..'|'..epoch..'|0x20000000000001|0xb|0xc|occupied') end
X4LAN_POSITIVE_SEAT_LIVE_TICK();assert(logs[#logs]:match(' DONE$'))
assert(logs[#logs-1]:match(mode=='candidate' and ' CANDIDATE$' or ' INCONCLUSIVE$'));assert(not table.concat(logs):find('private',1,true))
events['X4AuthorityPositiveSeatSearch.Refused']();assert(logs[#logs]:match(' ERROR FAULT$'))
assert(not pcall(X4LAN_POSITIVE_SEAT_LIVE_TICK))
