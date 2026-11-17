-- Real fixture owner, session, bootstrap, sampler and UDP; X4/MD are doubles.
local ffi = require('ffi')
ffi.cdef[[int usleep(unsigned int);]]
local Owner = dofile('tools/dev/authority_fixture_player_source.lua')
local Session = dofile('src/authority/lua/client_authority_motion_session.lua')
local Reader = dofile('src/authority/lua/client_authority_motion_reader.lua')
local Bootstrap = dofile('src/authority/lua/saved_baseline_source_bootstrap.lua')
local Sampler = dofile('src/authority/lua/source_motion_sampler.lua')
local IPC = dofile('src/authority/lua/source_motion_ipc.lua')
local Latest = dofile('src/authority/lua/fixture_player_latest_cache.lua')
local Barrier = dofile('src/authority/lua/fixture_player_freeze_barrier.lua')
local latest = os.getenv('TEST_LATEST_CACHE') == '1'
local drain = os.getenv('TEST_FREEZE_DRAIN') == '1'
local netmod = assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')), 'luaopen_x4lan_net'))()
local net = assert(netmod.open('127.0.0.1', assert(tonumber(os.getenv('TEST_NET_PORT')))))
local slot = assert(tonumber(os.getenv('TEST_FIXTURE_SLOT')))
local index, epoch, generation = slot + 2, ('1'):rep(32), ('2'):rep(32)
local lease, attempt, sector = ('5'):rep(32), ('6'):rep(32), 'sector_a'
local now, game, request, seen, callback, reader = 1, 10
local actor, boot_done = {}, false
local function make_session()
 return Session.new({enabled=true, fixture_slot=slot, epoch=epoch, generation=generation,
  index=index, baseline=4, include_orientation=true, latest_cache=latest, freeze_drain=drain, guard=function() return true end,
  grant=function() return true end, fault=function(reason) error(reason) end,
  register=function(fn) callback=fn; return true end,
  barrier_factory=function(opts)
   opts.enabled=true;opts.timeout=5;opts.clock=function() return now end;return Barrier.new(opts)
  end,
  latest_factory=function(opts)
   return Latest.new({enabled=true,grant={index=index,epoch=epoch,generation=generation,
    source=('7'):rep(32),frame=('8'):rep(32),sector=sector},max_age=1,clock=function() return now end,
    guard=opts.guard,authority=opts.authority,inspect=opts.inspect,validate_capture=opts.validate_capture,
    quiescent=opts.quiescent,reset_sampler=opts.reset_sampler})
  end,
  ipc_factory=function(opts)
   return IPC.new({enabled=true, lease=lease, attempt=attempt, epoch=epoch, generation=generation,
    timeout=5, clock=function() return now end, guard=opts.guard, fault=opts.fault, net=net, freeze_drain=drain,
    saved_baseline={limit=4,guard=function() return opts.guard() end}})
  end,
  reader_factory=function(opts)
   reader=Reader.new({enabled=true,fixture_slot=slot,epoch=epoch,generation=generation,index=index,
    baseline=4,sector=sector,include_orientation=true,latest_cache=latest,
    current_sector=function(value) if value==actor then return '2',sector end end,
    controlled=function(value) return value==actor end,
    bootstrap_nonce=('7'):rep(32),sampler_nonce=('8'):rep(32),guard=opts.guard,
    authority=opts.authority,stage_sample=opts.stage_sample,fault=opts.fault,
    bootstrap_factory=function(boot)
     return Bootstrap.new({enabled=true,epoch=epoch,baseline=4,nonce=boot.nonce,timeout=5,
      clock=function() return now end,guard=opts.guard,baseline_guard=function() return opts.guard() end,
      issue=function(_,_,args) request=args.request_id;return true end,
      parse=function(value) return value=='0x1' and actor or (value=='0x2' and {} or nil) end,
      inspect=function() return true end,complete=boot.complete})
    end,
    sampler_factory=function(sampler)
     return Sampler.new({enabled=true,epoch=epoch,generation=generation,nonce=sampler.nonce,
      max_tracks=1,scan_budget=1,include_orientation=true,interval=.1,timeout=5,min_dt=.02,max_dt=1,
      clock=function() return now end,guard=opts.guard,binding_guard=function() return false end,
      saved_baseline_limit=4,saved_baseline_guard=sampler.saved_baseline_guard,
      actor_key=function(value) return value==actor and '1' or nil end,fault=sampler.fault,
      reader_factory=function(row,_,id)
       return {start=function() request=id;return true end,tick=function() return true end,response=function()
        return true,{epoch=epoch,index=row.index,descriptor_atomic=false,sector_identity_proven=false,
         sector_macro=sector,local_sector_key='2',game_before_pose=game,game_after_pose=game,
         x=game,y=2,z=3,yaw=.1,pitch=.2,roll=.3}
       end}
      end})
    end})
   return reader
  end})
end
local owner = Owner.new({net=net,lease=lease,attempt=attempt,epoch=epoch,generation=generation, latest_cache=latest, freeze_drain=drain,
 seat_ready=function() return true end,paused=function() return false end,guard=function() return true end,
 make_session=make_session,fault=function(reason) error(reason) end})
while true do
 assert(owner:tick())
 if request and request~=seen then
  seen=request
  if not boot_done then
   callback(nil,request..'|'..epoch..'|'..index..'|ok|0x1|ship_macro|player|0x2|'..sector)
   boot_done=true
  else callback(nil,request..'|sample') end
 end
 now=now+.01;game=game+.01;ffi.C.usleep(1000)
end
