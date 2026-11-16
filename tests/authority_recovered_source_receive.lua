-- Exercise the actual new_x4 transport wrapper with simulated X4 and UDP.
local queued, sent, errors = {}, {}, {}
local receive_count, race_packet, pending_failure = 0, nil, false
local net = {
 send=function(_,packet) sent[#sent+1]=packet;return true end,
 pending=function()
  if pending_failure then return nil end
  if race_packet~=nil then
   queued[#queued+1]=race_packet;race_packet=nil;return false
  end
  return #queued>0
 end,
 receive=function()
  receive_count=receive_count+1
  local packet=table.remove(queued,1)
  -- Match the native net module: both invalid sizes return nil after reading.
  if packet=='' or (packet and #packet>768)then return nil end
  return packet
 end,
}
package.loadlib=function()
 return function()return {open=function(_,port)assert(port==2345);return net end}end
end
function GetCurRealTime()return 1 end
function RegisterEvent()return true end
function DebugError(message)errors[#errors+1]=message end
function X4LAN_AUTHORITY_RECOVERY_READY()return true end
X4LAN_RESOLVE_STRING={}
X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE={}
X4LAN_SAVED_BASELINE_SOURCE_BOOTSTRAP={new_x4=function()
 local state='idle'
 return {state=function()return state end,tick=function()return true end,
  expected_request=function()return nil end,close=function()state='closed';return true end}
end}
X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER={new_x4=function()
 local state='ready'
 return {state=function()return state end,expected_request=function()return nil end,
  close=function()state='closed';return true end}
end}
X4LAN_AUTHORITY_SOURCE_MOTION_IPC=dofile('src/authority/lua/source_motion_ipc.lua')
X4LAN_SOURCE_MOTION_SHUTDOWN=dofile('src/authority/lua/source_motion_shutdown.lua')
local module=dofile('tools/dev/authority_recovered_source_motion.lua')
local lease,attempt,epoch,generation=('1'):rep(32),('2'):rep(32),('c'):rep(32),('d'):rep(32)
local owner=assert(module.new_x4({port=2345,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
 nonce=('3'):rep(32),saved_nonce=('4'):rep(32),baseline=100,timeout=5,expected_save_path='/private/45841/save'}))
queued[1]=table.concat({'P',lease,attempt,'BOUND',epoch,generation},'|')
assert(owner:tick() and sent[#sent]:find('|ATTACHED|',1,true))
local mode=assert(arg[1])
local invalid=mode:find('empty',1,true) and '' or ('x'):rep(769)
if mode=='good' or mode:find('queued_',1,true)==1 or mode:find('late_',1,true)==1 or mode=='pending_error_stopped' then
 queued[1]=table.concat({'P',lease,attempt,'STOP',epoch,generation,'1'},'|')
 if mode:find('queued_',1,true)==1 then
  queued[2]=invalid
  assert(not owner:tick() and owner:state()=='failed')
  for _,packet in ipairs(sent)do assert(not packet:find('|STOPPED|',1,true))end
  return
 end
 assert(owner:tick() and owner:state()=='stopped' and sent[#sent]:find('|STOPPED|',1,true))
 if mode=='good' then return end
 if mode=='pending_error_stopped' then pending_failure=true else queued[1]=invalid end
 assert(not owner:tick() and owner:state()=='failed' and #errors>0)
 return
end
if mode=='pending_error' then pending_failure=true
else
 if mode:find('race',1,true)then
  race_packet=invalid;local before=receive_count
  assert(owner:tick() and receive_count==before and #queued==1)
 else queued[1]=invalid end
end
assert(not owner:tick() and owner:state()=='failed' and #errors>0)
for _,packet in ipairs(sent)do assert(not packet:find('|STOPPED|',1,true))end
