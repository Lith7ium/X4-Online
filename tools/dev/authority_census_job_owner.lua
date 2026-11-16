-- Default-off one-activation census experiment. No callbacks, sockets, or X4
-- work on import. One outer update owner calls tick; all I/O is nonblocking.
local M={}
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function natural(v)return finite(v) and v%1==0 and v>=1 and v<=9007199254740991 end
local function name(v)return type(v)=='string' and #v>0 and #v<=128 and v:match('^[%w_%-%.]+$')~=nil end
local function split(v)local r={};for x in (v..'|'):gmatch('(.-)|')do r[#r+1]=x end;return r end
function M.new(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert((o.role=='server' or o.role=='client') and token(o.lease) and token(o.attempt) and token(o.epoch) and token(o.nonce))
 assert(finite(o.timeout) and o.timeout>0 and o.timeout<=600 and (type(o.net)=='table' or type(o.net)=='userdata'))
 assert(finite(o.window) and o.window>=1 and o.window<=180)
 assert(o.defer_ack==nil or type(o.defer_ack)=='boolean')
 if o.defer_ack then assert(o.role=='server' and type(o.delivery)=='table' and type(o.delivery.new)=='function') end
 for _,k in ipairs({'clock','observe','guard','pause','resume','host_factory','descriptor_factory','witness_factory','baseline_request','log'})do assert(type(o[k])=='function',k..' required')end
 local phase='new';local failed,busy=false,false;local host,desc,witness,row,actor,descriptor,jobseq,windex,wmacro,gate,gate_event
 local peer={id='replica',incarnation=o.attempt}
 local last,deadline,host_deadline,paused_game,pending_check,check_counter=nil,nil,nil,nil,nil,0
 local prefix=table.concat({'CENSUS',o.lease,o.role,o.attempt,o.epoch},'|')
 local cmd=table.concat({'CMD',o.lease,o.role,o.attempt,o.epoch},'|')
 local function fail()
  if not failed then failed=true;phase='failed';pcall(o.log,'FAULT');pcall(function()o.net:send(prefix..'|FAULT')end) end
  return false
 end
 local function check(expect)
  if failed then return false end
  local ok,t=pcall(o.clock);if not ok or not finite(t) or t<0 or (last and t<last) or (deadline and t>=deadline) or (host_deadline and t>=host_deadline) then return fail() end;last=t
  local good,valid=pcall(o.guard);if not good or valid~=true or failed then return fail() end
  local observed,p,g=pcall(o.observe);if not observed or type(p)~='boolean' or not finite(g) or g<0 or (expect~=nil and p~=expect) then return fail() end
  if paused_game and (not p or g~=paused_game) then return fail() end
  local yes,after=pcall(o.clock);if not yes or not finite(after) or after<t or (deadline and after>=deadline) or (host_deadline and after>=host_deadline) then return fail() end;last=after
  return true,p,g
 end
 local function emit(label,rest,expect)
  if not check(expect) then return false end
  local text=prefix..'|'..label..(rest and '|'..rest or '');if #text>768 then return fail() end
  local ok,sent=pcall(o.net.send,o.net,text)
  if not ok or sent~=true or not check(expect) then return fail() end
  local logged=pcall(o.log,label);if not logged then return fail() end
  return true
 end
 local function fault()fail()end
 local function no_event(r)
  if failed or phase~='running' or row~=nil or type(r)~='table' or r.registry_mode~='attached' or
   r.baseline_count~=10054 or r.baseline_known_count~=0 or r.birth_confirmed~=false or r.delivery_confirmed~=false or
   r.coverage~='unknown' or not finite(r.observed) or r.observed<0 or r.observed>2147483647 or r.observed%1~=0 or r.acknowledged~=r.observed or
   (r.observed==0 and r.classification~='inconclusive_no_events') or
   (r.observed>0 and r.classification~='local_activations_observed') then return fail() end
  phase='no_event_stop';return true
 end
 local function report(r,a)
  if failed or phase~='running' or type(r)~='table' or r.epoch~=o.epoch or not natural(r.index) or not natural(r.sequence) or
   r.birth_confirmed~=false or r.delivery_confirmed~=false then return fail() end
  if r.classification=='new_registry_entry' then
   if r.index~=10055 or a==nil or row~=nil then return fail() end
   row={epoch=r.epoch,index=r.index,sequence=r.sequence,classification=r.classification};actor=a;jobseq=r.sequence;phase='captured'
  elseif o.defer_ack or (r.classification~='previously_observed' and r.classification~='previously_unobserved_existing_index') then return fail() end
  return true
 end
 local function request_witness(index,macro)
  witness=assert(o.witness_factory(index,macro));phase='witness_wait';assert(witness:start())
 end
 local function command(packet)
  if type(packet)~='string' or #packet>768 then return fail() end
  local p=split(packet)
  if #p<6 or table.concat({p[1],p[2],p[3],p[4],p[5]},'|')~=cmd then return fail() end
  if p[6]=='CHECK' and #p==7 then
   if pending_check or not p[7]:match('^[1-9]%d*$') or #p[7]>10 then return fail() end
   local n=tonumber(p[7]);if not n or n>2147483647 or n<=check_counter then return fail() end
   check_counter=n;pending_check=n;return true
  elseif p[6]=='START' and #p==6 and o.role=='server' and phase=='ready' then
   if not check(true) then return false end
   paused_game=nil;phase='resuming';local ok=pcall(o.resume);if not ok or not check(nil) then return fail() end;return true
  elseif p[6]=='WITNESS' and #p==9 and (phase=='descriptor_sent' or (o.role=='client' and phase=='ready')) then
   if not p[7]:match('^[1-9]%d*$') or not p[8]:match('^[1-9]%d*$') or #p[7]>16 or #p[8]>5 then return fail() end
   local seq,index=tonumber(p[7]),tonumber(p[8]);if not natural(seq) or not natural(index) or index>10054 or not name(p[9]) then return fail() end
   if o.role=='server' and (seq~=jobseq or not descriptor or p[9]~=descriptor.sector_macro) then return fail() end
   if not check(true) then return false end
   jobseq,windex,wmacro=seq,index,p[9];request_witness(index,wmacro);return true
  elseif p[6]=='DELIVERY_ACK' and #p==8 and o.defer_ack and phase=='finished' then
   if p[7]~=string.format('%.0f',jobseq) or p[8]~=string.format('%.0f',row.index) or not check(true) or not gate_event then return fail() end
   phase='ack_wait'
   local ok=gate:ack(peer,gate_event)
   if not ok or not check(true) then return fail() end
   return true
  end
  return fail()
 end
 local api={}
 local function queue_acked(epoch,sequence,index)
  if failed or busy or phase~='ack_wait' or not check(true) or not gate or
    epoch~=o.epoch or sequence~=jobseq or index~=row.index then return fail() end
  local ok=gate:source_acked(epoch,sequence,index)
  if not ok or not check(true) then return fail() end
  phase='source_ack_pending';return true
 end
 function api:baseline_event(value)
  if busy or failed or o.role~='client' or phase~='client_baseline' or value~=o.nonce..'|'..o.epoch..'|10054|ok' then return fail() end
  if not check(true) then return fail() end
  phase='ready_pending';return true
 end
 function api:descriptor_event(value)
  if busy or failed or phase~='descriptor_wait' or not desc or not check(true) then return fail() end
  local success,ok,r=pcall(desc.response,desc,value)
  if not success or not ok or type(r)~='table' or r.epoch~=o.epoch or r.index~=10055 or r.sequence~=jobseq or not name(r.macro) or not name(r.owner) or not name(r.sector_macro) or not finite(r.x) or not finite(r.y) or not finite(r.z) or math.abs(r.x)>10000000 or math.abs(r.y)>10000000 or math.abs(r.z)>10000000 or not check(true) then return fail() end
  descriptor={macro=r.macro,owner=r.owner,sector_macro=r.sector_macro,x=r.x,y=r.y,z=r.z}
  local closed,result=pcall(desc.close,desc);if not closed or result~=true or failed or not check(true) then return fail() end
  desc=nil;phase='descriptor_pending';return true
 end
 function api:witness_event(value)
  if busy or failed or phase~='witness_wait' or not witness or not check(true) then return fail() end
  local success,ok,r=pcall(witness.response,witness,value)
  if not success or not ok or type(r)~='table' or r.epoch~=o.epoch or r.index~=windex or r.sector_macro~=wmacro or r.local_witness_match~=true or not check(true) then return fail() end
  local closed,result=pcall(witness.close,witness);if not closed or result~=true or failed or not check(true) then return fail() end
  witness=nil;phase='witness_pending';return true
 end
 function api:fault()return fail()end
 function api:tick()
  if failed then return false end;if busy then return fail() end;busy=true
  local ok=pcall(function()
   if phase=='new' then
    local success,t=pcall(o.clock);assert(success and finite(t) and t>=0);last=t;deadline=t+o.timeout
    local valid,p,g=check(true);assert(valid);paused_game=g
    if o.role=='server' then
     host=assert(o.host_factory(report,fault,no_event,function() return paused_game~=nil and check(true)==true end,queue_acked));phase='attaching';assert(host:start())
    else phase='client_baseline';assert(o.baseline_request(o.epoch,o.nonce)==true) end
   end
   local expected=true
   if phase=='running' or phase=='captured' or phase=='no_event_stop' then expected=false elseif phase=='resuming' or phase=='pause_wait' or phase=='no_event_wait' then expected=nil end
   assert(check(expected))
   for _=1,4 do local packet=o.net:receive();if packet==nil then break end;assert(command(packet)) end
   if phase=='attaching' then
    local alive,s=host:tick();assert(alive and check(true));if s=='attached_wait_running' then phase='ready';assert(emit('READY',nil,true)) end
   elseif phase=='ready_pending' then
    phase='ready';assert(emit('READY',nil,true))
   elseif phase=='resuming' then
    local good,p=check(nil);assert(good);if not p then paused_game=nil;host_deadline=last+o.window+10;phase='running' end
   elseif phase=='running' then
    local alive,s=host:tick();assert(alive and s~='failed' and not failed)
   elseif phase=='captured' then
    assert(host:state()==(o.defer_ack and 'await_delivery' or 'waiting'));if o.defer_ack then host_deadline=nil end
    local good=pcall(o.pause);assert(good);phase='pause_wait'
   elseif phase=='pause_wait' then
    local valid,p,g=check(nil);assert(valid);if p then paused_game=g;phase='descriptor_start' end
   elseif phase=='no_event_stop' then
    assert(host:state()=='done');local good=pcall(o.pause);assert(good);phase='no_event_wait'
   elseif phase=='no_event_wait' then
    local valid,p,g=check(nil);assert(valid);if p then paused_game=g;phase='no_event_pending' end
   elseif phase=='no_event_pending' then
    assert(check(true) and host:state()=='done');phase='inconclusive';assert(emit('NO_EVENT',nil,true))
   elseif phase=='descriptor_start' then
    assert(check(true) and host:state()==(o.defer_ack and 'await_delivery' or 'waiting'));desc=assert(o.descriptor_factory(row,actor));phase='descriptor_wait';assert(desc:start())
   elseif phase=='descriptor_wait' then assert(check(true) and host:state()==(o.defer_ack and 'await_delivery' or 'waiting') and desc:tick())
   elseif phase=='descriptor_pending' then
    assert(check(true) and host:state()==(o.defer_ack and 'await_delivery' or 'waiting'));local d=descriptor;local vals={string.format('%.0f',jobseq),'10055',d.macro,d.owner,d.sector_macro,string.format('%.17g',d.x),string.format('%.17g',d.y),string.format('%.17g',d.z)}
    phase='descriptor_sent'
    if o.defer_ack then
     gate_event={epoch=o.epoch,generation=o.attempt,sequence=jobseq,index=row.index,descriptor={macro=d.macro,faction=d.owner,sector_macro=d.sector_macro,x=d.x,y=d.y,z=d.z}}
     gate=assert(o.delivery.new({enabled=true,generation=o.attempt,timeout=math.min(o.timeout,300),clock=o.clock,
      membership=function()return {peer}end,send=function()return emit('DESCRIPTOR',table.concat(vals,'|'),true)end,
      release=function(epoch,sequence,index)return host:confirm_delivery(epoch,sequence,index)end}))
     assert(gate:begin(gate_event))
    else assert(emit('DESCRIPTOR',table.concat(vals,'|'),true)) end
   elseif phase=='witness_wait' then assert(check(true) and witness:tick() and (not host or host:state()==(o.defer_ack and 'await_delivery' or 'waiting')))
   elseif phase=='witness_pending' then
    assert(check(true) and (not host or host:state()==(o.defer_ack and 'await_delivery' or 'waiting')));phase='finished';assert(emit('WITNESS_OK',table.concat({string.format('%.0f',jobseq),string.format('%.0f',windex),wmacro},'|'),true))
   elseif phase=='source_ack_pending' then
    assert(o.defer_ack and host:state()=='waiting' and gate:state()=='idle' and check(true))
    phase='source_acked';assert(emit('SOURCE_ACKED',table.concat({string.format('%.0f',jobseq),string.format('%.0f',row.index)},'|'),true))
   elseif phase=='descriptor_sent' or phase=='finished' or phase=='ready' or phase=='client_baseline' or phase=='inconclusive' then
    if host and (phase=='descriptor_sent' or phase=='finished') then assert(host:state()==(o.defer_ack and 'await_delivery' or 'waiting')) end
    if phase=='inconclusive' then assert(host and host:state()=='done') end
   elseif phase=='ack_wait' or phase=='source_acked' then
    assert(o.defer_ack and host and host:state()==(phase=='ack_wait' and 'front' or 'waiting'))
   else error('invalid phase') end
   if o.defer_ack and host and (host:state()=='await_delivery' or host:state()=='front') and phase~='running' and phase~='captured' and phase~='pause_wait' then assert(host:tick()) end
   if gate and (gate:state()=='waiting' or gate:state()=='released') then assert(gate:tick()) end
   if pending_check then
    local n=pending_check;pending_check=nil;local wanted=true
    if phase=='running' or phase=='captured' or phase=='no_event_stop' then wanted=false elseif phase=='resuming' or phase=='pause_wait' or phase=='no_event_wait' then wanted=nil end
    assert(emit('CHECKED',tostring(n),wanted))
   end
  end)
  busy=false;if not ok or failed then return fail() end;return true,phase
 end
 function api:state()return phase end
 function api:close()local ok=pcall(o.net.close,o.net);if not ok then return fail() end;return true end
 return api
end
return M
