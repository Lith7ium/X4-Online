local M=dofile('tools/dev/authority_sector_witness_runtime.lua');assert(M.new({})==nil and M.new_x4({})==nil)
local epoch,rid=string.rep('a',32),string.rep('b',32)
local function rig(mode)
 local now,game=1,20;local paused=true;local count=0;local requests={};local app
 local o={enabled=true,epoch=epoch,request_id=rid,index=10055,macro='sector_a_macro',timeout=5,
  clock=function()return now end,guard=function()return true end,paused=function()return paused end,game_time=function()return game end,
  issue=function(screen,op,args)requests[#requests+1]={screen=screen,op=op,args=args};return true end,
  verify=function(a,s)
   count=count+1;assert(a=='0x20000000000001' and s=='0x2')
   if mode=='moved' then return false elseif mode=='late' then now=7 elseif mode=='unpause' then paused=false elseif mode=='game' then game=21 elseif mode=='reentrant' then app:tick() elseif mode=='lost_second' and count==2 then return false end
   return true
  end}
 app=M.new(o);return app,requests
end
local line=rid..'|'..epoch..'|10055|ok|0x20000000000001|0x2|sector_a_macro'
local p,req=rig();assert(p:start());assert(req[1].screen=='X4AuthoritySectorWitnessRuntime' and req[1].args.index==10055)
local ok,row=p:response(line);assert(ok and row.local_witness_match and row.sector_macro=='sector_a_macro' and row.actor==nil and row.sector==nil and not row.cross_process_identity_proven and not row.atomic_snapshot_proven)
for _,mode in ipairs({'moved','late','unpause','game','reentrant','lost_second'}) do local x=rig(mode);assert(x:start());assert(not x:response(line),mode);assert(x:state()=='failed') end
for _,bad in ipairs({line:gsub('sector_a_macro','other'),line:gsub('10055','10056'),line:gsub('0x2','0xZ'),rid..'|'..epoch..'|10055|unavailable',line:gsub(rid,string.rep('c',32))}) do
 local x=rig();assert(x:start());assert(not x:response(bad)) end
print('sector witness tests passed')
