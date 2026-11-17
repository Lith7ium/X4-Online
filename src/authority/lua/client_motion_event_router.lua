-- Experimental permanent, exclusive local MD response router. No hooks or
-- game calls are installed until start; caller owns process/load/STOP fences.
local M={};local native_claimed=false
local MAX=9007199254740991
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function integer(v)return type(v)=='number' and v==v and v>=1 and v<=MAX and v%1==0 end
local function local_reference(value)
 local kind = type(value)
 return kind == 'userdata' or kind == 'cdata' or (kind == 'number' and integer(value))
end
local screens={['X4AuthorityReplicaMotionBind']='replica', ['X4AuthoritySavedBaselineMotionBind']='saved'}
local events={replica='X4AuthorityReplicaMotionBind.Result',saved='X4AuthoritySavedBaselineMotionBind.Result',
 apply='X4AuthoritySavedMotionApply.Result'}
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local fixed={};for k,v in pairs(o)do fixed[k]=v end;o=fixed
 assert(integer(o.max_generations) and o.max_generations<=4096 and integer(o.max_tracks) and o.max_tracks<=100000)
 assert(o.saved_apply==nil or o.saved_apply==true)
 assert(o.saved_apply_fixture==nil or (o.saved_apply==true and o.saved_apply_fixture=='recovery_enh_870'))
 if o.saved_apply then assert(integer(o.max_apply_requests) and o.max_apply_requests<=200000)
 else assert(o.max_apply_requests==nil) end
 for _,k in ipairs({'register','send','guard','retire_guard','fault'})do assert(type(o[k])=='function',k)end
 local state,busy,checking='new',false,false
 local current,pending=nil,nil
 local used_nonce,used_generation={},{};local count=0
 local api={}
 local function fail(reason)
  if state~='failed' then state='failed';pending=nil;pcall(o.fault,reason) end
  return false
 end
 local function context()
  if state=='failed' then return false end
  if checking then return fail('guard_reentrant')end
  checking=true
  local old=state;local ok,v=pcall(o.guard,current and current.generation or nil,current and current.nonce or nil,
   current and current.epoch or nil,current and current.owner or nil)
  checking=false
  return ok and v==true and state==old
 end
 local function run(fn)
  if busy or state=='failed' then return fail('reentrant_or_failed') end
  busy=true;local ok,v=pcall(fn);busy=false
  if not ok or state=='failed' then return fail('operation')end
  return v==nil and true or v
 end
 function api:start()
  return run(function()
   assert(state=='new' and context());state='registering'
   local routes=o.saved_apply and {'replica','saved','apply'} or {'replica','saved'}
   for _,route in ipairs(routes)do
    local event_route=route
    local ok=o.register(events[event_route],function(_,value)api:event(event_route,value)end)
    assert(ok==true and state=='registering' and context())
   end
   state='idle';assert(context())
  end)
 end
 function api:attach(generation,nonce,registry_epoch,owner)
  return run(function()
   assert(state=='idle' and not current and not pending and token(generation) and token(nonce) and token(registry_epoch) and generation~=nonce and
    (o.saved_apply_fixture==nil or registry_epoch=='4ba7be438ebb04ec5bb85fdb95b5a488') and
    not used_nonce[nonce] and not used_generation[nonce] and not used_generation[generation] and not used_nonce[generation] and count<o.max_generations and
    type(owner)=='table' and type(owner.state)=='function' and type(owner.event)=='function' and context())
   local state_fn,event_fn=owner.state,owner.event
   local apply_fn=o.saved_apply and owner.apply_event or nil
   assert(not o.saved_apply or type(apply_fn)=='function')
   local ok,s=pcall(state_fn,owner);assert(ok and (s=='new' or s=='ready') and owner.state==state_fn and owner.event==event_fn and (not o.saved_apply or owner.apply_event==apply_fn) and state=='idle' and context())
   count=count+1;used_nonce[nonce]=true;used_generation[generation]=true
   current={generation=generation,nonce=nonce,epoch=registry_epoch,owner=owner,owner_state=state_fn,
    owner_event=event_fn,owner_apply_event=apply_fn,requests={},tracks=0,apply_requests={},apply_count=0};state='active';assert(context())
  end)
 end
 -- The operation token is scoped to this owner's nonce. A post inspection is
 -- valid only for the same references as an earlier applying pre inspection.
 local function issue_saved_apply(screen, operation, arguments)
  assert(state == 'active' and current and not pending and operation == 'Inspect')
  assert(type(arguments) == 'table' and getmetatable(arguments) == nil)
  assert(arguments.epoch == current.epoch and integer(arguments.index) and context())
  assert(arguments.fixture == o.saved_apply_fixture and
   (arguments.fixture==nil or (arguments.fixture=='recovery_enh_870' and arguments.index==1318 and
    arguments.epoch=='4ba7be438ebb04ec5bb85fdb95b5a488')))

  local supplied_arguments = {}
  for name, value in pairs(arguments) do
   assert(name == 'request_id' or name == 'epoch' or name == 'index' or
    name == 'actor' or name == 'sector' or name == 'zone' or name == 'fixture')
   supplied_arguments[name] = value
  end
  assert(local_reference(arguments.actor) and local_reference(arguments.sector) and local_reference(arguments.zone))
  assert(type(arguments.request_id) == 'string')
  local request_nonce, operation_token, phase =
   arguments.request_id:match('^([0-9a-f]+)%-([0-9a-f]+)%-(%a+)$')
  assert(request_nonce == current.nonce and token(operation_token))
  assert(phase == 'pre' or phase == 'post')

  local owner = current.owner
  assert(owner.event == current.owner_event and owner.state == current.owner_state and
   owner.apply_event == current.owner_apply_event)
  local state_read, owner_state = pcall(current.owner_state, owner)
  assert(state_read and (owner_state == 'preflighting' or owner_state == 'applying'))
  assert(phase ~= 'post' or owner_state == 'applying')
  assert(owner.event == current.owner_event and owner.state == current.owner_state and
   owner.apply_event == current.owner_apply_event and context())

  local previous_request = current.apply_requests[operation_token]
  if phase == 'pre' then
   assert(not previous_request and current.apply_count < o.max_apply_requests)
   current.apply_count = current.apply_count + 1
   current.apply_requests[operation_token] = {
    index=arguments.index, actor=arguments.actor, sector=arguments.sector,
    zone=arguments.zone, fixture=arguments.fixture, owner_state=owner_state, post=false,
   }
  else
   assert(previous_request and previous_request.owner_state == 'applying' and not previous_request.post)
   assert(previous_request.index == arguments.index and previous_request.actor == arguments.actor and
    previous_request.sector == arguments.sector and previous_request.zone == arguments.zone and
    previous_request.fixture == arguments.fixture)
   previous_request.post = true
  end

  local request_id = arguments.request_id
  pending = {id=request_id, route='apply', owner_state=owner_state}
  local accepted = o.send(screen, operation, arguments)
  assert(accepted == true and state == 'active' and current and pending and pending.id == request_id)
  assert(getmetatable(arguments) == nil and owner.event == current.owner_event and
   owner.state == current.owner_state and owner.apply_event == current.owner_apply_event and context())
  for name, value in pairs(supplied_arguments) do assert(arguments[name] == value) end
  for name in pairs(arguments) do assert(supplied_arguments[name] ~= nil) end
 end
 function api:issue(screen,op,args)
  return run(function()
   if o.saved_apply and screen == 'X4AuthoritySavedMotionApply' then
    return issue_saved_apply(screen, op, args)
   end
   local route=screens[screen]
   assert(state=='active' and current and not pending and route and op=='Bind' and type(args)=='table' and getmetatable(args)==nil and
    type(args.request_id)=='string' and #args.request_id<=66 and integer(args.index) and args.epoch==current.epoch and
    type(args.sector_macro)=='string' and #args.sector_macro>=1 and #args.sector_macro<=128 and args.sector_macro:match('^[A-Za-z0-9_]+$') and
    ((route=='saved' and integer(args.baseline) and args.index<=args.baseline) or (route=='replica' and args.baseline==nil)) and context())
   local snapshot={};for k,v in pairs(args)do
    assert(k=='request_id' or k=='index' or k=='epoch' or k=='sector_macro' or k=='baseline');snapshot[k]=v
   end
   local nonce,index,sequence=args.request_id:match('^([0-9a-f]+)%-([1-9]%d*)%-([1-9]%d*)$')
   assert(nonce==current.nonce and index==string.format('%.0f',args.index) and #sequence<=16 and
    integer(tonumber(sequence)) and sequence==string.format('%.0f',tonumber(sequence)))
   local prior=current.requests[args.index]
   assert(not prior or tonumber(sequence)>prior)
   if not prior then assert(current.tracks<o.max_tracks);current.tracks=current.tracks+1 end
   current.requests[args.index]=tonumber(sequence)
   local id=args.request_id;pending={id=id,route=route}
   local accepted=o.send(screen,op,args)
   assert(accepted==true and state=='active' and current and pending and pending.id==id and
    args.request_id==id and args.index==tonumber(index) and getmetatable(args)==nil and context())
   for k,v in pairs(snapshot)do assert(args[k]==v)end
   for k in pairs(args)do assert(snapshot[k]~=nil)end
  end)
 end
 function api:event(route,value)
  return run(function()
   assert(state=='active' and current and pending and events[route] and pending.route==route and
    type(value)=='string' and #value<=256 and context())
   local id
   if route=='apply' then
    assert(o.saved_apply and (value:match('|ok$') or value:match('|refused$')))
    id=value:match('^([0-9a-f]+%-[0-9a-f]+%-%a+)|')
   else id=value:match('^([0-9a-f]+%-[1-9]%d*%-[1-9]%d*)|') end
   assert(id==pending.id)
   local owner=current.owner
   assert(owner.event==current.owner_event and owner.state==current.owner_state and
    (not o.saved_apply or owner.apply_event==current.owner_apply_event))
   local expected_state=route=='apply' and pending.owner_state or 'ready'
   if route=='apply' then
    local valid,prior_state=pcall(current.owner_state,owner);assert(valid and prior_state==expected_state)
   end
   local callback=route=='apply' and current.owner_apply_event or current.owner_event
   local ok,accepted=pcall(callback,owner,value,route)
   assert(ok and accepted==true and (route~='apply' or value:match('|ok$')) and
    state=='active' and current and current.owner==owner and pending and pending.id==id and context())
   assert(owner.event==current.owner_event and owner.state==current.owner_state and
    (not o.saved_apply or owner.apply_event==current.owner_apply_event))
   local good,owner_state=pcall(current.owner_state,owner)
   assert(good and owner_state==expected_state and owner.event==current.owner_event and owner.state==current.owner_state and
    (not o.saved_apply or owner.apply_event==current.owner_apply_event) and state=='active' and context())
   pending=nil
  end)
 end
 function api:retire()
  return run(function()
   assert(state=='active' and current and not pending and context())
   local owner=current.owner;assert(owner.event==current.owner_event and owner.state==current.owner_state and
    (not o.saved_apply or owner.apply_event==current.owner_apply_event))
   local ok,s=pcall(current.owner_state,owner)
   assert(ok and s=='stopped' and state=='active' and context())
   local good,confirmed=pcall(o.retire_guard,current.generation,current.nonce,owner)
   assert(good and confirmed==true and state=='active' and context())
   assert(owner.event==current.owner_event and owner.state==current.owner_state and
    (not o.saved_apply or owner.apply_event==current.owner_apply_event))
   local again,final=pcall(current.owner_state,owner);assert(again and final=='stopped' and owner.event==current.owner_event and owner.state==current.owner_state and
    (not o.saved_apply or owner.apply_event==current.owner_apply_event) and state=='active' and context())
   current=nil;state='idle';assert(context())
  end)
 end
 function api:supports_saved_apply()return o.saved_apply==true end
 function api:state()return state end
 function api:owns(generation,nonce,epoch,owner)
  local valid=state=='active' and current~=nil and current.generation==generation and current.nonce==nonce and
   current.epoch==epoch and current.owner==owner and owner.event==current.owner_event and owner.state==current.owner_state and
   (not o.saved_apply or owner.apply_event==current.owner_apply_event)
  if not valid or not context() then return false end
  return state=='active' and current~=nil and current.generation==generation and current.nonce==nonce and
   current.epoch==epoch and current.owner==owner and owner.event==current.owner_event and owner.state==current.owner_state and
   (not o.saved_apply or owner.apply_event==current.owner_apply_event)
 end
 return api
end
-- The enclosing manifest must load this module once; failed/partial native
-- registration never releases the claim within this Lua module incarnation.
function M.new_x4(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(not native_claimed,'motion event router already claimed')
 assert(type(RegisterEvent)=='function' and type(AddUITriggeredEvent)=='function')
 native_claimed=true
 local register,send=RegisterEvent,AddUITriggeredEvent
 local c={};for k,v in pairs(o)do c[k]=v end
 c.register=function(name,callback)return register(name,callback)~=false end
 c.send=function(screen,op,args)return send(screen,op,args)~=false end
 return M.new(c)
end
X4LAN_CLIENT_MOTION_EVENT_ROUTER=M
return M
