local ffi=require('ffi');local fake=ffi.load(assert(arg[1]),true)
local requests={};local epoch,nonce=string.rep('a',32),string.rep('b',32)
local fail_getter=false
function AddUITriggeredEvent(screen,op,args) requests[#requests+1]=args end
function ConvertStringToLuaID(value) return ffi.new('uint64_t',tonumber(value)) end
function ConvertIDTo64Bit(value) return ffi.new('uint64_t',value) end
function GetCurRealTime() return 1 end
function GetComponentData(id,field)
 local number=tonumber(id)
 if field=='hullpercent' then return 100 end
 if field=='assignedpilot' then
  if fail_getter and number==12 then error('unavailable') end
  if number==10 then return ffi.new('uint64_t',99) end
  return nil
 end
 error('unexpected field')
end
X4LAN_RESOLVE_STRING=dofile('tools/dev/authority_registry_resolve_string.lua')
local M=dofile('tools/dev/authority_player_seat_calibration.lua')
local function row(slot,actor,sector,reservation)
 return nonce..'-'..slot..'|'..epoch..'|'..slot..'|'..actor..'|'..sector..'|'..reservation
end
local cfg={enabled=true,epoch=epoch,nonce=nonce,timeout=10,expected_save_path='/tmp/45841/save'}
local probe=M.new_x4(cfg);local started,reason=probe:start();assert(started,reason);assert(requests[1].slot==0)
assert(probe:response(row(0,'0xa','0xb','occupied')))
assert(probe:response(row(1,'0xc','0xd','empty')))
local ok,result=probe:response(row(2,'0xe','0xb','empty'))
assert(ok and result.classification=='inconclusive' and not result.save_authorized)
assert(result.rows[1].assigned=='present' and result.rows[2].assigned=='nil_observed')
assert(result.rows[1].x==10 and result.rows[2].hull==100)
requests={};fail_getter=true;probe=M.new_x4(cfg);assert(probe:start())
assert(probe:response(row(0,'0xa','0xb','occupied')))
assert(not probe:response(row(1,'0xc','0xd','empty')) and probe:state()=='failed')
print('synthetic X4 seat getter adapter checks passed')
