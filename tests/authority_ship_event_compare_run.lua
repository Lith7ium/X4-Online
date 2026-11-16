local ffi=require('ffi')
ffi.cdef[[void TestReset(void);void TestPause(void);void TestResume(void);void TestAdvance(void);]]
local observer=assert(loadfile('tools/dev/authority_ship_event_compare.lua'))()
local resolve=assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
local function scenario(mode)
 ffi.C.TestReset();local logs,handlers,commands={},{},{};local now=1;local sent=false
 X4LAN_SHIP_EVENT_COMPARE=observer;X4LAN_RESOLVE_STRING=resolve
 X4LAN_CONFIG={authority_ship_event_compare_run=true,authority_load_save_path='/private/45841/save',
  authority_ship_event_compare_epoch=string.rep('a',32),authority_ship_event_compare_generation=string.rep('b',32),
  authority_ship_event_compare_capacity=128,authority_ship_event_compare_window=3}
 function RegisterEvent(name,cb)assert(not handlers[name]);handlers[name]=cb;return true end
 function AddUITriggeredEvent(_,op,args)commands[#commands+1]={op=op,args=args};return true end
 function GetCurRealTime()return now end
 function ConvertIDTo64Bit(v)return v end
 function ConvertStringToLuaID(v)if v=='42' then return 42 end end
 function Unpause()ffi.C.TestResume()end
 function Pause()ffi.C.TestPause()end
 function DebugError(v)logs[#logs+1]=v end
 assert(loadfile('tools/dev/authority_ship_event_compare_run.lua'))()
 for _=1,80 do
  X4LAN_EVENT_COMPARE_TICK()
  while #commands>0 do
   local c=table.remove(commands,1)
   if c.op=='Initialize' then handlers['X4AuthorityShipEventCompare.Initialized'](nil,c.args.generation)
   elseif c.op=='Front' then
    local v=c.args.request_id..'|empty'
    if mode~='empty' and not ffi.C.IsGamePaused() and not sent then
     sent=true;v=c.args.request_id..'|item|1|activation|41|0x2a'
    end
    handlers['X4AuthorityShipEventCompare.Result'](nil,v)
   elseif c.op=='Ack' then handlers['X4AuthorityShipEventCompare.Result'](nil,c.args.request_id..'|acked|'..c.args.sequence)
   else error('unexpected command') end
  end
  ffi.C.TestAdvance();now=now+1
  if mode=='pause' and sent and not ffi.C.IsGamePaused() then ffi.C.TestPause() end
  if #logs>0 and (logs[#logs]:match('DONE') or logs[#logs]:match('ERROR')) then break end
 end
 local joined=table.concat(logs,'\n')
 if mode=='empty' then assert(joined:match('READY') and joined:match('RUNNING') and joined:match('DONE 0') and not joined:match('ERROR'))
 elseif mode=='event' then assert(joined:match('ROW 1 activation 41 42') and joined:match('DONE 1') and not joined:match('ERROR'))
 else assert(joined:match('ERROR') and not joined:match('DONE')) end
end
for _,mode in ipairs({'empty','event','pause'})do scenario(mode)end
