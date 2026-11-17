-- Real recovered source, pair sampler, bootstrap, shutdown and UDP.
-- Only the X4/MD descriptor and saved actor are simulated; no X4 starts.
local ffi = require('ffi')
ffi.cdef[[int usleep(unsigned int);]]
local netlib = assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')), 'luaopen_x4lan_net'))()
local port = assert(tonumber(os.getenv('TEST_NET_PORT')))
local net = assert(netlib.open('127.0.0.1', port))

local owner_module = dofile('tools/dev/authority_recovered_source_motion.lua')
local bootstrap_module = dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local sampler_module = dofile('src/authority/lua/source_motion_sampler.lua')
local pair_module = dofile('src/authority/lua/source_motion_local_pair.lua')
local ipc_module = dofile('src/authority/lua/source_motion_ipc.lua')
local shutdown_module = dofile('src/authority/lua/source_motion_shutdown.lua')

local epoch, generation = ('c'):rep(32), ('d'):rep(32)
local source_nonce, saved_nonce, pair_nonce = ('3'):rep(32), ('5'):rep(32), ('9'):rep(32)
local pending, handler = {}, nil
local samples, reports = 0, 0

local owner = assert(owner_module.new({
 enabled=true, epoch=epoch, generation=generation, nonce=source_nonce, saved_nonce=saved_nonce,
 baseline=10054, clock=netlib.monotonic, timeout=5,
 running=function() return true end, guard=function() return true end,
 register=function(callback) assert(not handler); handler=callback; return true end,
 fault=function(reason) io.stderr:write('source fault: '..tostring(reason)..'\n'); os.exit(1) end,
 bootstrap_factory=function(options)
  options.timeout=5; options.clock=netlib.monotonic
  options.issue=function(_, _, request)
   assert(request.index==42)
   pending[#pending+1]={kind='bootstrap', request=request}
   return true
  end
  options.parse=function(value) return value end
  options.inspect=function() return true end
  return bootstrap_module.new(options)
 end,
 sampler_factory=function(options)
  options.clock=netlib.monotonic; options.max_tracks=1; options.scan_budget=1
  options.interval=.01; options.timeout=5; options.min_dt=.02; options.max_dt=1
  options.actor_key=function(actor) assert(actor=='0x29'); return '41' end
  options.reader_factory=function(row, actor, request)
   assert(row.index==42 and actor=='0x29')
   assert(options.nonce==pair_nonce, 'ordinary sampler must not be read in pair-delivery mode')
   return {
    start=function() pending[#pending+1]={kind='sample', request=request}; return true end,
    tick=function() return true end,
    response=function(_, value)
     assert(value==request..'|ok')
     samples=samples+1; assert(samples<=2)
     local sample_time = samples==1 and 1 or 1.5
     return true, {epoch=epoch, index=row.index, sequence=row.sequence,
      descriptor_atomic=false, sector_identity_proven=false,
      sector_macro='sector_a', local_sector_key='43',
      game_before_pose=sample_time, game_after_pose=sample_time,
      x=samples, y=2, z=3}
    end,
   }
  end
  return sampler_module.new(options)
 end,
 ipc_factory=function(options)
  options.enabled=true; options.lease=('1'):rep(32); options.attempt=('2'):rep(32)
  options.epoch=epoch; options.generation=generation; options.timeout=5
  options.clock=netlib.monotonic; options.net=net
  return ipc_module.new(options)
 end,
 shutdown_factory=shutdown_module.new,
 local_pair={nonce=pair_nonce, index=42, delivery=true, factory=pair_module.new,
  report=function(result)
   assert(result.status=='estimated' and result.first.source_time==1 and result.first.x==1 and
    result.second.source_time==1.5 and result.second.x==2 and result.velocity.x==2 and
    result.velocity.y==0 and result.velocity.z==0)
   reports=reports+1; assert(reports==1)
   return true
  end},
}))

local stopped = false
while true do
 assert(owner:tick(), 'source owner fault')
 while #pending>0 do
  local item=table.remove(pending, 1)
  if item.kind=='bootstrap' then
   handler(item.request.request_id..'|'..epoch..'|'..item.request.index..'|ok|0x29|ship_a|argon|0x2b|sector_a')
  else
   assert(item.kind=='sample')
   handler(item.request..'|ok')
  end
 end
 if owner:state()=='stopped' and not stopped then
  assert(samples==2 and reports==1 and #pending==0)
  stopped=true
  io.stdout:write('SOURCE_STOPPED\n'); io.stdout:flush()
 end
 -- Stay alive and keep the stopped-state/late-event fence active until the
 -- outer test has checked process identity and explicitly cleans us up.
 ffi.C.usleep(1000)
end
