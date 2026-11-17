-- Real source IPC/session/barrier; asynchronous X4 descriptor is a test double.
local Session=dofile('src/authority/lua/client_authority_motion_session.lua')
local IPC=dofile('src/authority/lua/source_motion_ipc.lua')
local Barrier=dofile('src/authority/lua/fixture_player_freeze_barrier.lua')
local function scenario(fail_mode)
 local lease,attempt,epoch,generation=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32)
 local input,output={},{};local clock=1;local callback;local expected=nil;local resets=0
 local net={send=function(_,value)output[#output+1]=value;return true end,
  receive=function()return table.remove(input,1)end,pending=function()return #input>0 end}
 local session=assert(Session.new{enabled=true,fixture_slot=1,epoch=epoch,generation=generation,index=3,baseline=4,
  include_orientation=true,latest_cache=true,freeze_drain=true,guard=function()return true end,
  grant=function()return true end,fault=function()end,register=function(fn)callback=fn;return true end,
  ipc_factory=function(x)return IPC.new{enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
   timeout=5,clock=function()return clock end,guard=x.guard,fault=x.fault,net=net,freeze_drain=true,
   saved_baseline={limit=4,guard=function()return true end}}end,
  barrier_factory=function(x)x.enabled=true;x.timeout=5;x.clock=function()return clock end;return Barrier.new(x)end,
  latest_factory=function(x)
   return {pause=function()assert(x.quiescent());resets=resets+1;return true end,
    resume=function()return true end,capture=function()return true end,pull=function()return nil,'empty' end}
  end,
  reader_factory=function(x)
   local phase='bootstrapping';expected=('e'):rep(32)
   return {start=function()return true end,state=function()return phase end,expected_request=function()return expected end,
    cache_context=function()return {} end,reset_sampling_baseline=function()return true end,
    tick=function()if phase=='sampling' and not expected then expected=('f'):rep(32)end;return true end,
    event=function(_,value)
     assert(value==expected..'|ok');expected=nil
     if phase=='bootstrapping' then phase='sampling' end
     return true
    end}
  end})
 local prefix='P|'..lease..'|'..attempt..'|'
 local context='|'..epoch..'|'..generation
 assert(session:start());input[1]=prefix..'BOUND'..context;assert(session:tick())
 input[1]=prefix..'REGISTER_SAVED'..context..'|1|3|4';assert(session:tick())
 callback(nil,('e'):rep(32)..'|ok');assert(session:tick())
 assert(expected==('f'):rep(32)) -- A descriptor event remains in flight.
 local count=#output
 input[1]=prefix..'FREEZE'..context..'|2';assert(session:tick())
 assert(#output==count and resets==0 and expected~=nil)
 if fail_mode=='timeout' then clock=6;assert(not session:tick());return end
 callback(nil,('f'):rep(32)..'|ok');assert(session:tick())
 assert(resets==1 and output[#output]==('S|'..lease..'|'..attempt..'|FROZEN'..context..'|2'))
 assert(session:quiescent())
 input[1]=prefix..'RESUME'..context..'|3';assert(session:tick())
 assert(output[#output]==('S|'..lease..'|'..attempt..'|RESUMED'..context..'|3'))
 assert(expected==('f'):rep(32)) -- Scheduling resumes only after acknowledgement.
 callback(nil,('f'):rep(32)..'|ok')
 assert(not session:quiescent()) -- An uncoordinated X4 pause must not reuse a stale cache.
end
scenario();scenario('timeout')
print('fixture source freeze drains asynchronous descriptor event')
