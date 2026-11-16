-- Read-only saved-baseline client owner, real UDP and fake local X4 ABI/MD.
local ffi=require('ffi');ffi.cdef[[int usleep(unsigned int);]]
local lib=assert(package.loadlib(assert(os.getenv('TEST_NET_LIB')),'luaopen_x4lan_net'))()
local net=lib.open('127.0.0.1',tonumber(assert(os.getenv('TEST_NET_PORT'))))
local resolve=dofile('tools/dev/authority_registry_resolve_string.lua')
local binding=dofile('src/authority/lua/replica_motion_binding.lua')
local saved=dofile('src/authority/lua/saved_baseline_motion_binding.lua')
local actual_buffer=dofile('src/authority/lua/motion_buffer.lua')
local buffer={new=function(options)
 assert(options.dimensions==3 and options.hold_only==true)
 local track=actual_buffer.new(options)
 return {push=function(_,sample,arrival)
  assert(sample.frame=='sector_a' and sample.pose[2]==2 and sample.pose[3]==3)
  if sample.sequence==1 then assert(sample.pose[1]==1 and sample.source_time==1 and sample.rate==nil)
  elseif sample.sequence==2 then assert(sample.pose[1]==2 and sample.source_time==1.5 and sample.rate and
   sample.rate[1]==2 and sample.rate[2]==0 and sample.rate[3]==0)
  else error('unexpected sample') end
  return track:push(sample,arrival)
 end}
end}
local core=dofile('src/authority/lua/motion_client_owner.lua')
local handlers,requests={},{}
function GetCurRealTime() return lib.monotonic() end
function RegisterEvent(name,fn) assert(not handlers[name]);handlers[name]=fn;return true end
function AddUITriggeredEvent(screen,op,args)
 assert(screen=='X4AuthoritySavedBaselineMotionBind' and op=='Bind' and args.baseline==10054 and args.index==42)
 if os.getenv('TEST_MOTION_BIND_TRACE')=='1' then io.stdout:write('BIND\n');io.stdout:flush() end
 requests[#requests+1]={args=args,when=lib.monotonic()+(tonumber(os.getenv('TEST_MOTION_BIND_DELAY')) or .08)};return true
end
function ConvertStringToLuaID(s)return ffi.new('uint64_t',tonumber(s))end
function ConvertIDTo64Bit(v)return v end
function GetComponentData(ref,...)assert(ref==41);return false,false,false end
local owner=assert(core.new_x4({enabled=true,lease=('7'):rep(32),attempt=('b'):rep(32),epoch=('c'):rep(32),generation=('d'):rep(32),nonce=('e'):rep(32),
 timeout=2,max_age=2,max_tracks=1,net=net,binding=binding,buffer=buffer,resolve=resolve,expected_save_path='/private/45841/save',
 guard=function()return true end,fault=function()end,
 stop=os.getenv('TEST_MOTION_STOP') and function()return os.getenv('TEST_MOTION_STOP')=='ok' end or nil,
 saved_baseline={enabled=true,baseline=10054,binding=saved,
 guard=function(e,n)return e==('c'):rep(32) and n==10054 end}}))
assert(owner:start())
while true do
 if #requests>0 and lib.monotonic()>=requests[1].when then
  local item=table.remove(requests,1)
  handlers['X4AuthoritySavedBaselineMotionBind.Result'](nil,item.args.request_id..'|Bound|42|0x29|0x2b')
 end
 assert(owner:tick(), 'saved motion owner tick failed')
 ffi.C.usleep(1000)
end
