local resolve=assert(loadfile('tools/dev/authority_registry_resolve_string.lua'))()
local module=assert(loadfile('tools/dev/authority_ship_event_compare.lua'))()
local a=assert(resolve.parse_hex('0x20000000000001'))
local b=assert(resolve.parse_hex('0x20000000000002'))
local function fixture(unsafe_reference)
 local handlers,commands,rows={},{},{};local now=1;local fault=nil
 function RegisterEvent(name,cb)assert(not handlers[name]);handlers[name]=cb;return true end
 function AddUITriggeredEvent(screen,op,args)assert(screen=='X4AuthorityShipEventCompare');commands[#commands+1]={op=op,args=args};return true end
 function GetCurRealTime()return now end
 function ConvertIDTo64Bit(v)return v end
 function ConvertStringToLuaID(v)
  if unsafe_reference then return 9007199254740994 end
  if v=='9007199254740993' then return a elseif v=='9007199254740994' then return b end
 end
 local app=assert(module.new_x4({enabled=true,epoch=string.rep('a',32),generation=string.rep('b',32),capacity=4,timeout=5,
  resolve=resolve,guard=function()return true end,report=function(row)rows[#rows+1]=row;return true end,fault=function(reason)fault=reason end}))
 local function event(name,v)assert(handlers['X4AuthorityShipEventCompare.'..name]);handlers['X4AuthorityShipEventCompare.'..name](nil,v)end
 assert(app:start());event('Initialized',string.rep('b',32))
 local function row(seq,kind,index,id)
  assert(app:tick());assert(commands[#commands].op=='Front')
  local req=commands[#commands].args.request_id
  event('Result',req..'|item|'..seq..'|'..kind..'|'..index..'|'..id)
  if app:state()~='failed' then
   assert(commands[#commands].op=='Ack');req=commands[#commands].args.request_id
   event('Result',req..'|acked|'..seq)
  end
 end
 return app,row,rows,function()return fault end,event,function(v)now=v end,commands
end
local app,row,rows=fixture()
row(1,'god',0,'0x20000000000001');row(2,'activation',0,'0x20000000000001');row(3,'galaxy_enter',42,'0x20000000000002')
assert(#rows==3 and rows[1].actor_key=='9007199254740993' and rows[2].actor_key==rows[1].actor_key)
assert(rows[3].actor_key=='9007199254740994' and rows[3].actor_key~=rows[1].actor_key)
assert(rows[1].kind=='god' and rows[2].kind=='activation' and rows[3].registry_index==42)
local bad,put,_,fault=fixture();put(1,'god',0,'9007199254740992');assert(bad:state()=='failed' and fault())
local unsafe,putunsafe,_,unsafe_fault=fixture(true);putunsafe(1,'god',0,'0x20000000000002');assert(unsafe:state()=='failed' and unsafe_fault())
local foreign,_,_,why,emit,_,cmd=fixture();assert(foreign:tick());emit('Result',cmd[#cmd].args.request_id..'|item|2|god|0|0x20000000000001');assert(foreign:state()=='failed' and why())
local stale,_,_,why2,ev,_,cmd2=fixture();assert(stale:tick());local old=cmd2[#cmd2].args.request_id;ev('Result',old..'|empty');assert(stale:tick());ev('Result',old..'|empty');assert(stale:state()=='failed' and why2())
local expired,_,_,reason,_,clock=fixture();assert(expired:tick());clock(7);expired:tick();assert(expired:state()=='failed' and reason())
local overflow,_,_,why3,ev3,_,commands=fixture();assert(overflow:tick());ev3('Faulted','capture_or_overflow');assert(overflow:state()=='failed' and why3() and commands[#commands].op=='Front')
assert(module.new({enabled=false})==nil)
print('event comparison local identity and fail-closed tests passed')
