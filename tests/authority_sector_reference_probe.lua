-- Synthetic callbacks and actor data only; no X4, native FFI or files.
local mode=arg[1];local callbacks={};local queue={};local sent={};local paused=true
local epoch=string.rep('a',32)
X4LAN_CONFIG={authority_sector_phase=mode=='load' and 'load' or 'save',authority_sector_epoch=epoch,authority_sector_deadline=10}
package.loaded.ffi={C={IsGamePaused=function() return paused end},cdef=function() end}
function RegisterEvent(name,fn) assert(not callbacks[name]);callbacks[name]=fn end
function DebugError(_) end
function GetCurRealTime() return 1 end
function Pause() error('unexpected pause') end
function ConvertStringToLuaID(...) assert(select('#',...)==1);return 'id:'..(...) end
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {
 factions=function() return {'argon'},false end,
 fleet_count=function() return 3 end,
 fleet=function() return {1,2,3},false end,
 key=function(id) return tostring(id)..'ULL' end,
 operational=function() return true end,is_ship=function() return true end,
 sector=function(id) return id==3 and 20 or 10 end,
} end}
function AddUITriggeredEvent(screen,op,args)
 assert(paused);sent[#sent+1]={screen,op,args};queue[#queue+1]={screen,op,args}
end
local function emit(name,value) assert(callbacks[name]);callbacks[name](nil,value) end
assert(loadfile('tools/dev/authority_sector_reference_probe.lua'))()
local function deliver()
 local item=table.remove(queue,1);assert(item)
 local screen,op,args=unpack(item);assert(args.epoch==epoch or op=='Status')
 if op=='Initialize' and screen=='X4AuthorityShipRegistry' then emit(screen..'.Initialized',epoch)
 elseif op=='Enroll' then
  if args.ship=='id:1' then emit(screen..'.Enrolled',1)
  elseif args.ship=='id:3' then emit(screen..'.Enrolled',2)
  else error('selected wrong actor') end
 elseif op=='Initialize' then assert(args.index1==1 and args.index2==2);emit(screen..'.Initialized',epoch)
 elseif op=='Status' then emit(screen..'.Epoch',epoch);emit(screen..'.Count',2)
 elseif op=='Verify' then emit(screen..'.Verified',epoch)
 else error('unexpected operation') end
end
if mode=='load' then
 assert(not X4LAN_AUTHORITY_SECTOR_READY());deliver();deliver();assert(X4LAN_AUTHORITY_SECTOR_READY())
 assert(#sent==2 and sent[1][2]=='Status' and sent[2][2]=='Verify')
elseif mode=='pause-loss' then
 assert(not X4LAN_AUTHORITY_SECTOR_READY())
 while #queue==0 do assert(not X4LAN_AUTHORITY_SECTOR_READY()) end
 paused=false
 assert(not pcall(deliver));assert(#sent==1)
 assert(not pcall(X4LAN_AUTHORITY_SECTOR_READY))
else
 assert(not X4LAN_AUTHORITY_SECTOR_READY())
 while #queue==0 do assert(not X4LAN_AUTHORITY_SECTOR_READY()) end
 while #queue>0 do deliver() end
 assert(X4LAN_AUTHORITY_SECTOR_READY())
 assert(#sent==5 and sent[2][3].ship=='id:1' and sent[3][3].ship=='id:3')
end
print('sector probe synthetic '..mode..' passed')
