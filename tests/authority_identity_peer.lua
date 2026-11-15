-- Focused helper contract test; does not model X4 save/load.
local callbacks,requests,props,now={}, {}, {}, 0
X4LAN_CONFIG={authority_identity_phase='save'}
function RegisterEvent(name,fn) callbacks[name]=fn end
function AddUITriggeredEvent(screen,control) requests[#requests+1]=screen..':'..control end
function ConvertIDTo64Bit(v) return v end
function ConvertStringToLuaID(v) return v end
function SetComponentName(id,name) props[id]=name end
function GetComponentData(id) return props[id], 'ship_arg_s_fighter_01_a_macro' end
function GetCurRealTime() return now end
function DebugError() end
dofile('tools/dev/authority_identity_probe.lua')
assert(not X4LAN_IDENTITY_READY() and requests[1]=='X4AuthorityIdentity:Spawn')
callbacks['X4AuthorityIdentity.Spawned'](nil,2)
assert(requests[2]=='X4AuthorityIdentity:Inspect')
callbacks['X4AuthorityIdentity.Actor1'](nil,101)
callbacks['X4AuthorityIdentity.Actor2'](nil,102)
callbacks['X4AuthorityIdentity.Inspected'](nil,2)
assert(X4LAN_IDENTITY_READY())
assert(props['101']=='Authority identity alpha 7181' and props['102']=='Authority identity beta 7182')
