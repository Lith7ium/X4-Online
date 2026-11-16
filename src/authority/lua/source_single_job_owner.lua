-- Opt-in source activations, one held head at a time. One existing onUpdate owner drives this
-- module; importing it installs nothing. This is not a ship-birth detector.
local M={}
local MAX=9007199254740991
local QUEUE_MAX=2147483647
local function token(x)return type(x)=='string' and #x==32 and x:match('^[0-9a-f]+$')~=nil end
local function integer(x)return type(x)=='number' and x==x and x%1==0 and x>=1 and x<=MAX end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 assert(token(c.lease) and token(c.attempt) and token(c.epoch) and token(c.generation) and token(c.descriptor_request))
 assert(c.lease~=c.attempt and c.lease~=c.epoch and c.lease~=c.generation and c.attempt~=c.epoch and c.attempt~=c.generation and c.epoch~=c.generation)
 assert(integer(c.sequence) and c.sequence==1 and integer(c.index))
 assert(c.continuous==nil or type(c.continuous)=='boolean')
 local continuous=c.continuous==true
 assert(not continuous or c.max_events==nil,'conflicting event limits')
 assert(c.max_events==nil or (integer(c.max_events) and c.max_events>=2 and c.max_events<=QUEUE_MAX))
 local max_events=c.max_events or 1
 if not continuous then assert(c.index<=MAX-max_events+1,'registry index capacity') end
 assert(type(c.timeout)=='number' and c.timeout==c.timeout and c.timeout>0 and c.timeout<=120)
 for _,k in ipairs({'clock','guard','host_factory','descriptor_factory','register_descriptor','fault'})do assert(type(c[k])=='function',k..' required')end
 assert(type(c.ipc)=='table' and type(c.ipc.new)=='function' and type(c.gate)=='table' and type(c.gate.new)=='function')
 assert((type(c.net)=='table' or type(c.net)=='userdata') and type(c.net.send)=='function' and type(c.net.receive)=='function')
 local state,busy='new',false;local failed=false;local last,deadline,row,actor,desc,acknowledged,source_confirmed
 local completed=0
 local host,ipc;local api={}
 local function fail(reason)
  if not failed then failed=true;state='failed';pcall(c.fault,reason)end
  return false
 end
 local function check()
  if failed then return false end
  local prior=state
  local ok,t=pcall(c.clock)
  if not ok or failed or state~=prior or type(t)~='number' or t~=t or t<0 or t==math.huge or (last and t<last) or (deadline and t>=deadline) then return false end
  last=t;local good,v=pcall(c.guard)
  if not good or v~=true or failed or state~=prior then return false end
  local yes,u=pcall(c.clock)
  if not yes or failed or state~=prior or type(u)~='number' or u~=u or u<t or u==math.huge or (deadline and u>=deadline) then return false end
  last=u;return true
 end
 local function send(s)
  local prior=state
  if #s>768 or not check() then return false end
  local ok,v=pcall(c.net.send,c.net,s)
  return ok and v==true and not failed and state==prior and check()
 end
 local function identity(prefix,op)return table.concat({prefix,c.lease,c.attempt,op,c.epoch,c.generation},'|')end
 local function reported(r,a)
  if failed or state~='observing' or row or type(r)~='table' or r.epoch~=c.epoch or r.sequence~=c.sequence+completed or
     r.index~=c.index+completed or r.classification~='new_registry_entry' or r.birth_confirmed~=false or r.delivery_confirmed~=false or a==nil then return fail('unexpected_source_entry')end
  row={epoch=r.epoch,sequence=r.sequence,index=r.index,classification=r.classification};actor=a;state='selected';return true
 end
 local function source_acked(e,s,i)
  if failed or state~='delivering' or acknowledged or source_confirmed or not row or e~=c.epoch or s~=row.sequence or i~=row.index then return fail('unexpected_source_ack') end
  acknowledged=true;return true -- avoid reentering IPC from the host callback
 end
 local function window_done(summary)
  if failed or not continuous or state~='observing' or row or type(summary)~='table' or
     summary.observed~=completed or summary.acknowledged~=completed or summary.registry_mode~='attached' or
     summary.birth_confirmed~=false or summary.delivery_confirmed~=false or summary.coverage~='unknown' then
   return fail('unexpected_window_done')
  end
  state='finishing';return true
 end
 host=assert(c.host_factory(reported,source_acked,fail,window_done))
 ipc=assert(c.ipc.new({enabled=true,lease=c.lease,attempt=c.attempt,epoch=c.epoch,generation=c.generation,
  timeout=c.timeout,clock=c.clock,guard=function()return state=='delivering' and check()end,gate=c.gate,
  send=function(raw)return state=='delivering' and send(raw)end,
  release=function(e,s,i)
   if state~='delivering' or not check() then return false end
   local accepted=host:confirm_delivery(e,s,i)
   return accepted==true and state=='delivering' and check()
  end}))
 function api:start()
  if busy or state~='new' then return fail('start_state')end
  busy=true
  local ok=pcall(function()
   assert(check());deadline=last+c.timeout;assert(c.register_descriptor(function(_,value)api:descriptor_event(value)end)==true and not failed and state=='new')
   state='binding';assert(send(identity('S','HELLO')))
  end)
  busy=false;if not ok then return fail('start')end;return true
 end
 function api:descriptor_event(value)
  if busy or failed or state~='reading' or not desc then return fail('unexpected_descriptor')end
  busy=true
  local ok=pcall(function()
   assert(check() and host:state()=='await_delivery')
   local accepted,d=desc:response(value);assert(accepted==true and type(d)=='table')
   assert(getmetatable(d)==nil and d.epoch==c.epoch and row and d.sequence==row.sequence and d.index==row.index and
          d.descriptor_atomic==false and d.sector_identity_proven==false and d.birth_confirmed==false)
   local keys={'epoch','sequence','index','descriptor_atomic','sector_identity_proven','birth_confirmed',
               'macro','owner','sector_macro','x','y','z'}
   local sample={};for _,k in ipairs(keys)do sample[k]=d[k]end
   assert(check() and host:state()=='await_delivery' and getmetatable(d)==nil)
   for _,k in ipairs(keys)do assert(d[k]==sample[k])end
   state='delivering'
   assert(ipc:candidate({epoch=c.epoch,generation=c.generation,sequence=row.sequence,index=row.index,
    descriptor={macro=sample.macro,faction=sample.owner,sector_macro=sample.sector_macro,x=sample.x,y=sample.y,z=sample.z}}))
   desc=nil
  end)
  busy=false;if not ok then return fail('descriptor')end;return true
 end
 function api:tick()
  if busy or failed or state=='new' or state=='done' then return fail('tick_state')end
  busy=true
  local ok=pcall(function()
   assert(check())
   if state=='binding' then
    local p=c.net:receive()
    if p~=nil then
     assert(p==identity('P','BOUND'));state='attaching';assert(host:start())
    end
   elseif state=='attaching' then
    assert(host:tick());if host:state()=='attached_wait_running' then
     assert(send(identity('S','ATTACHED')));state='await_go'
    end
    assert(c.net:receive()==nil)
   elseif state=='await_go' then
    assert(host:state()=='attached_wait_running' and host:tick() and host:state()=='attached_wait_running')
    local p=c.net:receive()
    if p~=nil then
     assert(p==identity('P','GO'));state='observing';assert(send(identity('S','GO_READY')))
     -- Continuous sessions use the host/descriptor/IPC operation deadlines and
     -- the supervisor lifecycle after GO, not a lifetime measured from start.
     if continuous then deadline=nil end
    end
   elseif state=='observing' or state=='selected' then
    assert(host:tick())
    if state=='selected' then
     assert(host:state()=='await_delivery' and row and actor~=nil)
     local request=c.descriptor_request
     if continuous or max_events>1 then request=request:sub(1,24)..string.format('%08x',row.sequence) end
     desc=assert(c.descriptor_factory(row,actor,request));state='reading';assert(desc:start())
    end
    assert(c.net:receive()==nil)
   elseif state=='reading' then
    assert(host:tick() and desc:tick() and c.net:receive()==nil)
   elseif state=='delivering' then
    if acknowledged then
     assert(host:state()=='waiting');assert(row and ipc:source_acked(c.epoch,row.sequence,row.index));acknowledged=false;source_confirmed=true
    elseif not source_confirmed then
     assert(host:tick())
    end
    if ipc:state()~='idle' then assert(ipc:tick())end
    local p=c.net:receive()
    if p~=nil then assert(ipc:packet(p))end
    if ipc:state()=='idle' then
     assert(source_confirmed and row);completed=completed+1
     row,actor,source_confirmed=nil,nil,nil
     if not continuous and completed==max_events then state='done';deadline=nil else
      assert(completed<QUEUE_MAX and c.index<=MAX-completed,'queue or registry capacity');state='observing'
     end
    end
   elseif state=='finishing' then
    assert(send(identity('S','FINISHED')..'|'..string.format('%.0f',completed)));state='done';deadline=nil
   else error('invalid phase')end
   assert(not failed and (state=='done' or check()))
  end)
  busy=false;if not ok then return fail('tick')end;return true
 end
 function api:state()return state end
 return api
end

-- Production bindings remain explicitly experimental. net is the one already
-- connected x4lan_net socket; its peer/PID and sole onUpdate owner are fenced
-- externally. The host attaches the paused saved registry and never resets it.
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(type(c.host)=='table' and type(c.host.new_x4)=='function' and type(c.probe)=='table')
 assert(type(c.descriptor)=='table' and type(c.descriptor.new_x4)=='function')
 assert(type(c.external_guard)=='function' and type(c.fault)=='function' and type(c.expected_save_path)=='string')
 assert(type(c.resolve)=='table' and c.resolve==X4LAN_RESOLVE_STRING and type(c.resolve.actor_u64)=='function' and type(ConvertIDTo64Bit)=='function')
 assert(type(RegisterEvent)=='function' and type(GetCurRealTime)=='function')
 local fixed={};for k,v in pairs(c)do fixed[k]=v end;c=fixed
 local ffi=require('ffi');ffi.cdef[[bool IsPlayerValid(void);bool IsGamePaused(void);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]]
 local C=ffi.C;local last_game,paused_game,owner
 local exact_actor,convert_actor=c.resolve.actor_u64,ConvertIDTo64Bit
 local function environment()
  local p=C.GetSaveFolderPath()
  if p==nil or p==ffi.NULL or ffi.string(p):gsub('\\','/'):gsub('/+$','')~=c.expected_save_path or not C.IsPlayerValid() then return false end
  local phase=owner and owner:state() or 'new'
  if (phase=='new' or phase=='binding' or phase=='attaching' or phase=='await_go') and not C.IsGamePaused() then return false end
  if (phase=='selected' or phase=='reading' or phase=='delivering' or phase=='finishing') and C.IsGamePaused() then return false end
  return true
 end
 local function guard()
  if not environment() or c.external_guard()~=true or not environment() then return false end
  local t=tonumber(C.GetCurrentGameTime())
  if not t or t~=t or t<0 or t==math.huge or (last_game and t<last_game) or not environment() then return false end
  local phase=owner and owner:state() or 'new'
  if not paused_game then paused_game=t end
  if (phase=='new' or phase=='binding' or phase=='attaching' or phase=='await_go') and t~=paused_game then return false end
  if phase=='observing' and C.IsGamePaused() and t~=paused_game then return false end
  if (phase=='selected' or phase=='reading' or phase=='delivering' or phase=='finishing') and t<=paused_game then return false end
  last_game=t;return true
 end
 local opts={};for k,v in pairs(c)do opts[k]=v end
 opts.clock=GetCurRealTime;opts.guard=guard
 opts.register_descriptor=function(callback)
  return RegisterEvent('X4AuthorityJobDescriptorProbe.Result',callback)~=false
 end
 opts.host_factory=function(report,acked,fault,window_done)
  return c.host.new_x4({enabled=true,epoch=c.epoch,baseline={},capacity=c.capacity,window=c.window,timeout=c.host_timeout,
   attach_saved_registry=true,exclusive_registry_consumer=true,expected_last=c.index-1,
   expose_actor=true,defer_ack=true,delivery_timeout=c.timeout,probe=c.probe,context_guard=guard,
   raw_actor_guard=function(actor)
    local original=exact_actor(actor);if not original then return false end
    local converted=exact_actor(convert_actor(actor));return converted~=nil and converted==original
   end,
   expected_save_path=c.expected_save_path,report=report,queue_acked=acked,
   done=function(summary)if c.continuous then return window_done(summary) end;return fault('no_selected_event')end,fault=fault})
 end
 opts.descriptor_factory=function(row,actor,request)
  return c.descriptor.new_x4({enabled=true,epoch=c.epoch,request_id=request,timeout=c.host_timeout,
   row=row,actor=actor,expected_save_path=c.expected_save_path,guard=guard})
 end
 owner=assert(M.new(opts));return owner
end
X4LAN_AUTHORITY_SOURCE_SINGLE_JOB_OWNER=M
return M
