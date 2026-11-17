-- Real UDP library, motion owner and FFI binding; simulated correlated MD.
local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);void TestLive(bool);]]
local netmod=assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')),'luaopen_x4lan_net'))()
local net=netmod.open('127.0.0.1',tonumber(assert(os.getenv('TEST_NET_PORT'))))
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local binding=dofile('src/authority/lua/replica_motion_binding.lua')
local core=dofile('src/authority/lua/motion_client_owner.lua')
local actual_buffer=dofile('src/authority/lua/motion_buffer.lua')
local buffer={new=function(opts)
 local full_pose=os.getenv('TEST_FULL_POSE')=='1'
 assert(opts.dimensions==(full_pose and 6 or 3) and opts.hold_only==true)
 local track=actual_buffer.new(opts)
 return {push=function(_,sample,arrival)
  local two=os.getenv('TEST_TWO_SAMPLES')=='1'
  assert(sample.pose[1]==(two and sample.sequence==2 and 2 or 1) and sample.pose[2]==2 and sample.pose[3]==3 and sample.source_time>=0)
  if full_pose then assert(sample.pose[4]==.1 and sample.pose[5]==.2 and sample.pose[6]==.3) end
  if two and sample.sequence==2 then assert(sample.rate and sample.rate[1]==2 and sample.rate[2]==0 and sample.rate[3]==0)
  elseif os.getenv('TEST_EXPECT_RATE')=='1' then assert(sample.rate and sample.rate[1]==4 and sample.rate[2]==5 and sample.rate[3]==6)
  else assert(sample.rate==nil) end
  if full_pose and sample.rate then assert(sample.rate[4]==.4 and sample.rate[5]==.5 and sample.rate[6]==.6) end
  return track:push(sample,arrival)
 end}
end}
local lease,attempt,epoch,gen=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32)
local callback,queue,owner=nil,{},nil;local start=netmod.monotonic()
function GetCurRealTime()return netmod.monotonic()end
function RegisterEvent(name,fn)assert(name=='X4AuthorityReplicaMotionBind.Result' and not callback);callback=fn;return true end
function AddUITriggeredEvent(screen,op,args)
 assert(screen=='X4AuthorityReplicaMotionBind' and op=='Bind')
 queue[#queue+1]={args=args,due=netmod.monotonic()+.2};return true
end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)assert(ref==41);return false,false,false end
owner=assert(core.new_x4({enabled=true,lease=lease,attempt=attempt,epoch=epoch,generation=gen,nonce=('e'):rep(32),
 timeout=2,max_age=1,max_tracks=10,net=net,binding=binding,buffer=buffer,resolve=resolve,
 expected_save_path='/private/45841/save',guard=function()return true end,fault=function()end,
 audit=function(index,seq,sector,source_time)
  assert(index==42 and seq>=1 and sector=='sector_a' and source_time>0)
  return os.getenv('TEST_BAD_AUDIT')~='1'
 end}))
assert(owner:start())
while netmod.monotonic()-start<5 do
 if #queue>0 and netmod.monotonic()>=queue[1].due then
  local item=table.remove(queue,1);local value=item.args.request_id..'|Bound|'..item.args.index..'|0x29|0x2b'
  if os.getenv('TEST_BAD_MD')=='1' then value=('f'):rep(32)..'-1|Bound|'..item.args.index..'|0x29|0x2b' end
  if os.getenv('TEST_DESPAWN')=='1' then ffi.C.TestLive(false)end
  callback(nil,value)
 end
 if not owner:tick() then break end
 ffi.C.usleep(1000)
end
