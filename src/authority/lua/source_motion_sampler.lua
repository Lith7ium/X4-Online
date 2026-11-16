-- Default-off source motion sampler. The caller owns the sole X4 update hook,
-- MD event router and transport; this module neither registers nor writes X4.
local M={}
local MAX=9007199254740991
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function integer(v)return type(v)=='number' and v==v and v>=1 and v<=MAX and v%1==0 end
local function finite(v)return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge end
local function name(v)return type(v)=='string' and #v>=1 and #v<=128 and v:match('^[A-Za-z0-9_]+$')~=nil end
local function valid_row(r,epoch)
 return type(r)=='table' and getmetatable(r)==nil and r.epoch==epoch and integer(r.index) and integer(r.sequence)
  and r.classification=='new_registry_entry'
end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 local c={};for k,v in pairs(o)do c[k]=v end
 assert(token(c.epoch) and token(c.generation) and token(c.nonce))
 assert(c.epoch~=c.generation and c.epoch~=c.nonce and c.generation~=c.nonce)
 for _,k in ipairs({'clock','guard','binding_guard','actor_key','reader_factory','fault'})do assert(type(c[k])=='function',k..' required')end
 assert(integer(c.max_tracks) and c.max_tracks<=1000000 and integer(c.scan_budget) and c.scan_budget<=1024)
 assert(finite(c.interval) and c.interval>0 and c.interval<=60 and finite(c.timeout) and c.timeout>0 and c.timeout<=120)
 assert(finite(c.min_dt) and finite(c.max_dt) and c.min_dt>0 and c.min_dt<=c.max_dt and c.max_dt<=60)
 local state,busy='ready',false
 local entries,order,actors={}, {}, {}
 local cursor,request_number,last_clock,last_game,pending=1,0,nil,nil,nil
 local api={}
 local function fail(reason)
  if state~='failed' then state='failed';pcall(c.fault,reason)end
  return false
 end
 local function check()
  if state=='failed' or state=='closed' then return false end
  local before=state
  local ok,t=pcall(c.clock)
  if not ok or state~=before or not finite(t) or t<0 or (last_clock and t<last_clock) or (pending and t>=pending.deadline)then return false end
  last_clock=t
  local g,v=pcall(c.guard)
  if not g or v~=true or state~=before then return false end
  local yes,u=pcall(c.clock)
  if not yes or state~=before or not finite(u) or u<t or (pending and u>=pending.deadline)then return false end
  last_clock=u;return true
 end
 local function row_ok(e)
  return valid_row(e.row,c.epoch) and e.row.index==e.index and e.row.sequence==e.source_sequence
 end
 local function checked_binding(entry)
  if not row_ok(entry) then return false end
  local old=state
  local ok,key=pcall(c.actor_key,entry.actor)
  if not ok or state~=old or key~=entry.key then return false end
  local good,allowed=pcall(c.binding_guard,entry.row,entry.actor)
  return good and allowed==true and state==old and row_ok(entry) and check()
 end
 function api:register(row,actor)
  if busy or state~='ready' or not valid_row(row,c.epoch) or actor==nil or entries[row.index] or #order>=c.max_tracks then return fail('register')end
  local copy={epoch=row.epoch,index=row.index,sequence=row.sequence,classification=row.classification}
  busy=true
  local ok=pcall(function()
   assert(check())
   local key=c.actor_key(actor)
   assert(type(key)=='string' and key:match('^[1-9]%d*$') and not actors[key])
   local entry={row=copy,index=copy.index,source_sequence=copy.sequence,actor=actor,key=key,next_due=0,sequence=0}
   assert(checked_binding(entry) and not entries[copy.index] and not actors[key])
   entries[copy.index]=entry;actors[key]=copy.index;order[#order+1]=copy.index
  end)
  busy=false;if not ok then return fail('register')end;return true
 end
 function api:tick()
  if busy or state=='failed' or state=='closed' then return fail('tick')end
  busy=true
  local ok=pcall(function()
   assert(check())
   if state=='pending' then assert(pending.reader:tick()==true and check());return end
   assert(state=='ready')
   local n=#order
   for _=1,math.min(c.scan_budget,n)do
    if cursor>n then cursor=1 end
    local entry=entries[order[cursor]];cursor=cursor+1
    if entry and last_clock>=entry.next_due then
     assert(checked_binding(entry) and request_number<MAX)
     request_number=request_number+1
     local request=c.nonce:sub(1,16)..string.format('%016x',request_number)
     local reader=assert(c.reader_factory(entry.row,entry.actor,request))
     assert(checked_binding(entry))
     pending={entry=entry,reader=reader,request=request,deadline=last_clock+c.timeout}
     state='pending';assert(reader:start()==true and check());break
    end
   end
  end)
  busy=false;if not ok then return fail('tick')end;return true
 end
 function api:expected_request()return state=='pending' and pending.request or nil end
 function api:event(value)
  if busy or state~='pending' or type(value)~='string' or value:sub(1,32)~=pending.request or value:sub(33,33)~='|' then return fail('event')end
  busy=true
  local result
  local ok=pcall(function()
   assert(check());local e=pending.entry;assert(checked_binding(e))
   local accepted,sample=pending.reader:response(value)
   assert(accepted==true and type(sample)=='table' and getmetatable(sample)==nil and sample.epoch==c.epoch and sample.index==e.row.index
    and sample.sequence==e.row.sequence and sample.descriptor_atomic==false and sample.sector_identity_proven==false
    and name(sample.sector_macro) and type(sample.local_sector_key)=='string' and sample.local_sector_key:match('^[1-9]%d*$')
    and finite(sample.game_before_pose) and finite(sample.game_after_pose)
    and sample.game_before_pose>=0 and sample.game_after_pose>=sample.game_before_pose and sample.game_after_pose<=1e12
    and finite(sample.x) and finite(sample.y) and finite(sample.z)
    and math.abs(sample.x)<=1e7 and math.abs(sample.y)<=1e7 and math.abs(sample.z)<=1e7)
   local sampled={sector_macro=sample.sector_macro,local_sector_key=sample.local_sector_key,game_after_pose=sample.game_after_pose,x=sample.x,y=sample.y,z=sample.z}
   assert(checked_binding(e) and e.sequence<MAX)
   sample=sampled
   local t=sample.game_after_pose;assert(not last_game or t>=last_game,'source game clock regressed')
   local previous=e.previous;local velocity=nil
   if previous then
    assert(t>=previous.last_time,'source game clock regressed')
    assert(not e.sent_sector or e.sent_sector~=sample.sector_macro or
     e.sent_local_sector_key==sample.local_sector_key,'sent local sector identity changed under same macro')
    assert(previous.sector~=sample.sector_macro or previous.local_sector_key==sample.local_sector_key,
     'local sector identity changed under same macro')
    if previous.sector==sample.sector_macro and previous.local_sector_key==sample.local_sector_key then
     local dt=t-previous.time
     if dt>=c.min_dt and dt<=c.max_dt then
      local x,y,z=(sample.x-previous.x)/dt,(sample.y-previous.y)/dt,(sample.z-previous.z)/dt
      if finite(x) and finite(y) and finite(z) and math.abs(x)<=5000 and math.abs(y)<=5000 and math.abs(z)<=5000 then velocity={x=x,y=y,z=z}end
     end
    end
   end
   if previous and t==previous.last_time then
    if previous.sector~=sample.sector_macro or previous.local_sector_key~=sample.local_sector_key then
     e.previous={sector=sample.sector_macro,local_sector_key=sample.local_sector_key,time=t,last_time=t,
      x=sample.x,y=sample.y,z=sample.z}
    end
    e.next_due=last_clock+c.interval;pending=nil;state='ready';result=nil;return
   end
   -- The receiver has only seen the last emitted sector, not suppressed reads.
   if e.sent_sector and e.sent_sector~=sample.sector_macro then velocity=nil end
   local v={version=1,epoch=c.epoch,generation=c.generation,index=e.row.index,sequence=e.sequence+1,
    sector_macro=sample.sector_macro,source_time=t,x=sample.x,y=sample.y,z=sample.z,velocity=velocity}
   assert(check() and state=='pending')
   result=v
   last_game=t;e.sequence=e.sequence+1;e.sent_sector=sample.sector_macro;e.sent_local_sector_key=sample.local_sector_key;e.next_due=last_clock+c.interval
   if not previous or previous.sector~=sample.sector_macro or previous.local_sector_key~=sample.local_sector_key or t-previous.time>=c.min_dt then
    e.previous={sector=sample.sector_macro,local_sector_key=sample.local_sector_key,time=t,last_time=t,x=sample.x,y=sample.y,z=sample.z}
   else previous.last_time=t end
   pending=nil;state='ready'
  end)
  busy=false;if not ok then return fail('sample')end;return true,result
 end
 function api:state()return state end
 function api:close()if busy or state=='pending' then return fail('close')end;state='closed';return true end
 return api
end
-- This factory uses the existing native descriptor reader. The existing X4
-- owner must route the single correlated event by expected_request() and drive
-- tick; registering a second handler or update script is deliberately avoided.
function M.new_x4(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 local frozen={};for k,v in pairs(c)do frozen[k]=v end;c=frozen
 assert(type(c.descriptor)=='table' and type(c.descriptor.new_x4)=='function')
 assert(type(c.resolve)=='table' and type(c.resolve.actor_u64)=='function' and c.resolve==X4LAN_RESOLVE_STRING)
 assert(type(c.expected_save_path)=='string' and type(c.guard)=='function' and type(c.binding_guard)=='function'
  and type(GetCurRealTime)=='function' and type(GetComponentData)=='function' and type(ConvertStringToLuaID)=='function'
  and type(ConvertIDTo64Bit)=='function')
 local opts={};for k,v in pairs(c)do opts[k]=v end
 local resolve_actor,new_descriptor=c.resolve.actor_u64,c.descriptor.new_x4
 local component_data,to_lua_id,to64,external_binding=GetComponentData,ConvertStringToLuaID,ConvertIDTo64Bit,c.binding_guard
 opts.clock=GetCurRealTime
 opts.actor_key=function(actor)
  local v=resolve_actor(actor);if not v then return nil end
  local s=tostring(v):gsub('ULL$','');return s:match('^[1-9]%d*$') and s or nil
 end
 opts.binding_guard=function(row,actor)
  local function free()
   local key=opts.actor_key(actor);if not key then return false end
   local original=resolve_actor(actor);if not original then return false end
   local id=to_lua_id(key);if not id then return false end
   local from_id=resolve_actor(id);if not from_id or from_id~=original then return false end
   local roundtrip=resolve_actor(to64(id));if not roundtrip or roundtrip~=original then return false end
   local docked,docking,stored=component_data(id,'isdocked','isdocking','isinternallystored')
   return docked==false and docking==false and stored==false
  end
  return free() and external_binding(row,actor)==true and free()
 end
 opts.reader_factory=function(row,actor,request)
  return new_descriptor({enabled=true,epoch=c.epoch,request_id=request,timeout=c.timeout,
   row=row,actor=actor,expected_save_path=c.expected_save_path,guard=c.guard,include_local_sector=true})
 end
 return M.new(opts)
end
X4LAN_AUTHORITY_SOURCE_MOTION_SAMPLER=M
return M
