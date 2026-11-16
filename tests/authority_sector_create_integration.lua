-- Fake-X4 end-to-end owner/driver integration; no native process.
local mode=arg[1];local events,queue,records,diagnostics={},{},{},{};local paused=true;local now=1;local count=1;local creates_sent=0
local epoch,nonce=string.rep('a',32),string.rep('b',32)
package.loaded.ffi={NULL={},typeof=function()return true end,cdef=function()end,string=function(s)return s end,C={
 GetSaveFolderPath=function()return '/private/45841/save' end,IsPlayerValid=function()return true end,IsGamePaused=function()return paused end,
 GetCurrentGameTime=function()return 3 end,IsValidComponent=function()return true end,IsComponentOperational=function()return true end,
 IsComponentClass=function(_,c)return c=='ship' or c=='sector' end,GetContextByClass=function(a)return a==51 and 61 or 62 end,
 GetObjectPositionInSector=function()return {x=-400,y=100000,z=500} end}}
local idmap={['0x33']=51,['0x34']=52,['0x3d']=61,['0x3e']=62}
X4LAN_RESOLVE_STRING={parse_hex=function(v)return idmap[v] end,actor_u64=function(v)if type(v)=='number' and v>=1 and v<=9007199254740991 and v%1==0 then return v end end}
X4LAN_AUTHORITY_SHIP_ENGINE={new=function()return {fleet_count=function()return count end,fleet=function()
 local rows={};for i=1,count do rows[i]=49+i end;return rows,false end} end}
function GetCurRealTime()return now end
function ConvertStringToLuaID(v)return tonumber(v) end
function ConvertIDTo64Bit(v)return mode=='conversion_failure' and v+1 or v end
function GetComponentData()return 'ship_arg_s_fighter_01_a_macro' end
function RegisterEvent(n,f)assert(not events[n]);events[n]=f end
function AddUITriggeredEvent(screen,op,args)
 queue[#queue+1]={screen=screen,op=op,args=args}
 if op=='Create' then
  creates_sent=creates_sent+1
  if mode=='issue_exception' then error('sensitive exception must not be logged') end
  if mode=='issue_pause_loss' then paused=false end
 end
 return true
end
local module=assert(loadfile('tools/dev/authority_sector_create_driver.lua'))()
local owner=assert(assert(loadfile('tools/dev/authority_sector_create_owner.lua'))().new_x4({enabled=true,exclusive_events=true,
 expected_save_path='/private/45841/save',epoch=epoch,nonce=nonce,macros={'sector_a','sector_b'},driver_module=module,
 report=function(row)records[#records+1]=row;return true end,
 diagnostic=function(text)
  diagnostics[#diagnostics+1]=text
  if mode=='before_dispatch_error' and text=='DISPATCH before Create' then error('log failure') end
  if mode=='slow_before_dispatch' and text=='DISPATCH before Create' then now=now+6 end
  if mode=='slow_after_dispatch' and text=='DISPATCH after Create accepted' then now=now+6 end
 end}))
local started=owner:start()
if mode=='conversion_failure' then
 assert(not started and owner:state()=='failed' and creates_sent==0)
 local text=table.concat(diagnostics,'|');assert(text:find('ADAPTER_FAIL count_conversion',1,true));assert(not text:find(epoch,1,true));return
end
assert(started)
for _=1,40 do
 now=now+.1;local item=table.remove(queue,1);if not item then break end
 local s,op,a=item.screen,item.op,item.args
 if op=='Preflight' then events[s..'.Preflight'](nil,a.request_id..'|'..epoch..'|sector_a|sector_b')
 elseif op=='Initialize' then events[s..'.Initialized'](nil,epoch)
 elseif op=='Create' then
  if a.index==3 and count==1 then count=2 elseif a.index==4 and count==2 then count=3 end
  events[s..'.Created'](nil,a.index)
 elseif op=='Inspect' then
  local id=a.index;local actor=id==3 and '0x33' or '0x34';local sector=id==3 and '0x3d' or '0x3e'
  local macro=id==3 and 'sector_a' or 'sector_b';local loc=id==3 and 'remote' or 'local'
  if mode=='mismatch' and id==4 then sector='0x3d' end
  events[s..'.Result'](nil,a.request_id..'|'..epoch..'|'..id..'|'..actor..'|'..sector..'|'..macro..'|'..loc)
 else error('unexpected operation') end
 if owner:state()=='pending_fence' or owner:state()=='failed' then break end
 owner:update()
end
if mode=='ok' or mode=='late_event' then
 assert(owner:state()=='pending_fence' and #records==6 and count==3)
 local done,why=owner:update();assert(done==false and why=='pending_fence')
 if mode=='late_event' then events['X4AuthorityShipCreateReceiver.Created'](nil,3);assert(owner:state()=='failed') end
else assert(owner:state()=='failed') end
local text=table.concat(diagnostics,'|')
if mode=='ok' then
 local expected={}
 for _,op in ipairs({'Preflight','Initialize','Create','Inspect','Create','Inspect','Create','Inspect','Create','Inspect','Inspect','Inspect'}) do
  expected[#expected+1]='DISPATCH before '..op;expected[#expected+1]='DISPATCH after '..op..' accepted'
 end
 assert(#diagnostics==#expected)
 for i,v in ipairs(expected) do assert(diagnostics[i]==v) end
end
assert(not text:find(epoch,1,true) and not text:find(nonce,1,true) and not text:find('sector_a',1,true) and not text:find('sensitive exception',1,true))
if mode=='before_dispatch_error' or mode=='slow_before_dispatch' then assert(creates_sent==0 and text:find('DISPATCH before Create',1,true) and not text:find('DISPATCH after Create',1,true)) end
if mode=='issue_exception' then assert(creates_sent==1 and text:find('DISPATCH before Create',1,true) and text:find('DISPATCH after Create exception',1,true)) end
if mode=='issue_pause_loss' then assert(creates_sent==1 and text:find('DISPATCH before Create|DISPATCH after Create accepted',1,true) and text:find('ADAPTER_FAIL guard',1,true)) end
if mode=='slow_after_dispatch' then assert(creates_sent==1 and text:find('DISPATCH after Create accepted',1,true) and text:find('DRIVER_FAIL created timeout',1,true)) end
if mode=='late_event' then assert(text:find('DRIVER_FAIL done late_event',1,true) and text:find('OWNER_FAIL callback',1,true)) end
print('sector-create integration fake '..mode..' passed')
