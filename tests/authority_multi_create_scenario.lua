local client=dofile('tools/dev/authority_multi_create_client.lua')
local scenario=dofile('tools/dev/authority_multi_create_scenario.lua')
local epoch,nonce=string.rep('a',32),string.rep('b',32)
local function run(mode)
 local now,good=1,true;local queue,rows={},{}
 local desc={{index=3,macro='ship_a',sector='sector_a',owner='argon',seed=7183,x=1,y=2,z=3,witness_index=1},
             {index=4,macro='ship_a',sector='sector_b',owner='argon',seed=7183,x=1,y=2,z=3,witness_index=2}}
 local s=assert(scenario.new({enabled=true,client=client,epoch=epoch,nonce=nonce,baseline=2,timeout=5,descriptors=desc,
  clock=function()return now end,guard=function()return good end,
  issue=function(_,op,args)queue[#queue+1]={op=op,args=args};return true end,
  inspect=function(actor)if mode=='bad_inspect' then return '0',false end;return actor=='0x29' and '41' or '42',true end,
  emit=function(row)rows[#rows+1]=row end}))
 assert(s:tick())
 for step=1,9 do
  local req=table.remove(queue,1);assert(req)
  local id=req.args.request_id;local actor=req.args.index==3 and '0x29' or '0x2a'
  local v=req.op=='Initialize' and (id..'|Initialized|'..epoch) or
   req.op=='Create' and (id..'|Created|'..req.args.index..'|'..actor) or
   (id..'|Inspected|'..req.args.index..'|'..actor..'|0x2b')
  if mode=='wrong_id' and step==2 then v='bad|Created|3|0x29' end
  if mode=='pause_loss' and step==3 then good=false end
  local ok=s:event(v)
  if (mode=='wrong_id' and step==2) or (mode=='pause_loss' and step==3) or (mode=='bad_inspect' and step==3) then
   assert(not ok and not s:tick());return
  end
  assert(ok);assert(s:tick())
 end
 now=now+0.6;assert(s:tick())
 assert(table.concat(rows,';')=='ROW create 3 sector_a;ROW create 4 sector_b;ROW replay 3 sector_a;ROW replay 4 sector_b;DONE')
 assert(not s:event('late'))
end
for _,mode in ipairs({'success','wrong_id','pause_loss','bad_inspect'})do run(mode)end
