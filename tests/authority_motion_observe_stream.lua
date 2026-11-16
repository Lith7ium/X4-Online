-- Offline only: actual owner and setter with fake binding, clock and engine.
local owner_module=dofile('src/authority/lua/motion_client_owner.lua')
local writer_module=dofile('src/authority/lua/saved_motion_apply.lua')
local A,B,E,G,N=('a'):rep(32),('b'):rep(32),('c'):rep(32),('d'):rep(32),('e'):rep(32)
local D=('f'):rep(64)
local function run(mode)
 local input,out,cb,logs,faults={},{},{},{},{}
 local now,game,position,writes,actor=1,10,0,0,'42'
 local socket={send=function(_,v)out[#out+1]=v;return true end,receive=function()return table.remove(input,1)end}
 local function request(n)return string.format('%032x',n)end
 local saved={enabled=true,baseline=10054,guard=function()return true end,register=function(f)cb.saved=f;return true end,
  factory=function(o)local sequence;return {begin=function(_,v)sequence=v.sequence;return true end,tick=function()return true end,
   event=function()assert(o.capture_binding(actor,'43','44',1318,sequence));return o.complete({epoch=E,generation=G,index=1318,sequence=sequence,sector_macro='cluster_115_sector001_macro'})end}end}
 local owner=assert(owner_module.new({enabled=true,lease=A,attempt=B,epoch=E,generation=G,nonce=N,timeout=5,max_age=3,max_tracks=10,
  clock=function()return now end,guard=function()return true end,net=socket,fault=function(r)faults[#faults+1]=r end,
  register=function()return true end,factory=function()error('unexpected replica')end,saved_baseline=saved,
  buffer={new=function()return {push=function()return true end}end},
  saved_apply={enabled=true,immediate_readback=true,observe_limit=mode~='default' and 2 or nil,
   register=function(f)cb.apply=f;return true end,factory=function(opt)
    opt.clock=function()return now end;opt.game=function()return game end
    opt.issue=function(id)cb.last_id=id;return true end
    opt.inspect=function()
     if mode=='inspect_failure' and writes>0 then error('failure after write')end
     return {x=position,y=0,z=0,yaw=0,pitch=0,roll=0}
    end
    opt.write=function(_,p)writes=writes+1;position=p.x;return true end
    opt.log=function(line)logs[#logs+1]=line;return true end
    return assert(writer_module.new(opt))
   end}}))
 assert(owner:start())
 local function bind(seq,x,t)
  input[1]=table.concat({'M',A,B,'BIND',request(seq*10+1),E,G,'1318',tostring(seq),'cluster_115_sector001_macro',D,tostring(t),tostring(x),'0','0','-','-','-'},'|')
  if not owner:tick() then return false end
  cb.saved(nil,'ok');return owner:state()=='ready'
 end
 local function preflight(seq)
  local id=request(seq*10+2)
  input[1]=table.concat({'M',A,B,'PREFLIGHT',id,E,G,'1318',tostring(seq),D},'|')
  assert(owner:tick());cb.apply(nil,id..'-pre|ok');assert(owner:tick())
  return out[#out]
 end
 local function observe(seq,operation)
  local id=request(seq*10+3)
  input[1]=table.concat({'M',A,B,operation or 'OBSERVE',id,E,G,'1318',tostring(seq),D},'|')
  if not owner:tick() then return false end
  cb.apply(nil,id..'-pre|ok')
  if owner:state()=='failed' then return false end
  assert(owner:tick())
  assert(out[#out]==table.concat({'R',A,B,'OBSERVED',id,E,G,'1318',tostring(seq),D},'|'))
  return true
 end
 if mode=='without_preflight' then assert(bind(1,10,10));assert(not observe(1) and writes==0);return end
 assert(bind(1,10,10));assert(preflight(1):sub(-5)=='READY')
 if mode=='default' then assert(not observe(1));assert(writes==0);return end
 if mode=='wrong_operation' then assert(not observe(1,'APPLY'));assert(writes==0);return end
 if mode=='inspect_failure' then assert(not observe(1) and writes==1 and owner:state()=='failed');assert(not owner:tick());return end
 assert(observe(1) and writes==1)
 if mode=='replay_observe' then assert(not observe(1) and writes==1);return end
 if mode=='replay' then assert(not bind(1,20,11) and writes==1);return end
 if mode=='same_time' then assert(not bind(2,20,10) and writes==1);return end
 if mode=='actor_changed' then actor='45';assert(not bind(2,20,11) and writes==1);return end
 if mode=='near' then
  assert(bind(2,11,11));assert(preflight(2):sub(-4)=='NEAR')
  assert(not observe(2) and writes==1);return
 end
 assert(bind(2,20,11));assert(preflight(2):sub(-5)=='READY');assert(observe(2) and writes==2)
 assert(not bind(3,30,12) and writes==2)
 local immediate=0
 for _,line in ipairs(logs)do
  if line:match('^IMMEDIATE ')then immediate=immediate+1 end
  assert(not line:match('^READBACK ') and not line:match('^POST_OBSERVED '))
 end
 assert(immediate==2)
end
for _,m in ipairs({'normal','default','wrong_operation','inspect_failure','without_preflight','replay_observe','replay','same_time','actor_changed','near'})do run(m)end
print('bounded observe stream owner/setter passed with fake engine')
