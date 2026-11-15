-- Fake-X4 end-to-end owner/driver integration; no native process.
local mode=arg[1];local events,queue,records={},{},{};local paused=true;local now=1;local count=1
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
function ConvertIDTo64Bit(v)return v end
function GetComponentData()return 'ship_arg_s_fighter_01_a_macro' end
function RegisterEvent(n,f)assert(not events[n]);events[n]=f end
function AddUITriggeredEvent(screen,op,args)queue[#queue+1]={screen=screen,op=op,args=args};return true end
local module=assert(loadfile('tools/dev/authority_sector_create_driver.lua'))()
local owner=assert(assert(loadfile('tools/dev/authority_sector_create_owner.lua'))().new_x4({enabled=true,exclusive_events=true,
 expected_save_path='/private/45841/save',epoch=epoch,nonce=nonce,macros={'sector_a','sector_b'},driver_module=module,
 report=function(row)records[#records+1]=row;return true end}))
assert(owner:start())
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
if mode=='ok' then
 assert(owner:state()=='pending_fence' and #records==6 and count==3)
 local done,why=owner:update();assert(done==false and why=='pending_fence')
else assert(owner:state()=='failed') end
print('sector-create integration fake '..mode..' passed')
