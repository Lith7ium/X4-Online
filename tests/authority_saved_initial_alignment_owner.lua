-- Real owner lifecycle with injected binding/preparation/native factory, no X4.
local core = dofile('src/authority/lua/motion_client_owner.lua')
local mode = assert(os.getenv('ALIGNMENT_OWNER_CASE'))
local epoch = '4ba7be438ebb04ec5bb85fdb95b5a488'
local input, output = {}, {}
local event_callback, owner
local factory_calls, preparations = 0, 0
local reported_uncertain = false
local request_sequence = 0
local net = {send=function(_, value) output[#output+1]=value; return true end,
 receive=function() return table.remove(input,1) end}
local function binding_factory(options)
 return {begin=function(_,sample) request_sequence=sample.sequence; return true end,
  tick=function() return true end, close=function() return true end,
  event=function()
   assert(options.capture_binding('41','43','45',1318,request_sequence))
   assert(options.complete({epoch=epoch,generation=('d'):rep(32),index=1318,
    sequence=request_sequence,sector_macro='cluster_06_sector001_macro'}))
   return true
  end}
end
local options = {enabled=true, lease=('a'):rep(32), attempt=('b'):rep(32), epoch=epoch,
 generation=('d'):rep(32), nonce=('e'):rep(32), timeout=5, max_age=1, max_tracks=1,
 clock=function() return 1 end, guard=function() return true end, net=net,
 register=function() return true end, factory=binding_factory,
 buffer={new=function() return {} end}, stop=function() return true end,
 fault=function(_, uncertain) reported_uncertain=reported_uncertain or uncertain end,
 saved_baseline={enabled=true,baseline=2000,guard=function() return true end,
  register=function(callback) event_callback=callback; return true end,factory=binding_factory},
 saved_replica_control={enabled=true,factory=function()
  return {prepare=function() preparations=preparations+1; return true end,
   tick=function() return true end, state=function() return 'prepared' end,
   release=function() return true end, outcome_uncertain=function() return false end}
 end},
 saved_playback={enabled=true, initial_alignment_fixture='recovery_enh_870',factory=function(factory_options)
  factory_calls=factory_calls+1
  assert(preparations == 1 and factory_options.prepared() == true)
  assert(factory_options.initial_sample.arrival == 1)
  local sample=factory_options.initial_sample.snapshot
  assert(sample.sequence == 1 and sample.source_time == 77 and sample.pose[1] == 1000)
  if mode == 'uncertain_factory' then
   factory_options.initial_alignment_state.uncertain = true
   factory_options.fault('initial_alignment_failed',true,'initial_alignment','setter')
   return nil
  elseif mode == 'reentrant_stop' then
   factory_options.initial_alignment_state.uncertain = true
   assert(not owner:tick()) -- A reentrant operation must fence the owner before any BOUND.
   return nil
  end
  factory_options.initial_alignment_state.used = true
  return {push=function() return true end,tick=function() return true end,
   stop=function() return true end,state=function() return 'stale' end,outcome_uncertain=function() return false end}
 end}}
owner=assert(core.new(options));assert(owner:start())
local function bind(sequence)
 input[1]=table.concat({'M',('a'):rep(32),('b'):rep(32),'BIND',('f'):rep(32),epoch,('d'):rep(32),
  '1318',tostring(sequence),'cluster_06_sector001_macro',('1'):rep(64),tostring(76+sequence),
  '1000','25','-10','0','0','0'},'|')
 assert(owner:tick());event_callback(nil,'correlated')
end
bind(1)
if mode ~= 'success' then
 assert(owner:state() == 'failed' and owner:outcome_uncertain() and reported_uncertain and #output == 1)
 return
end
assert(owner:state() == 'ready' and #output == 2 and factory_calls == 1)
bind(2)
assert(owner:state() == 'ready' and #output == 3 and factory_calls == 1 and preparations == 2)
