local M=dofile('tools/dev/authority_sector_pair_create.lua')
assert(M.new({})==nil)
local now=1;local game=12;local captured={};local registry='X4AuthorityShipCreateReceiver';local inspect='X4AuthorityPairCreateInspect'
local function setup(role,opts)
 opts=opts or {};local n=10;local items={};local out={};local complete={}
 local settings={enabled=true,role=role,epoch=string.rep('a',32),attempt=string.rep('b',32),nonce=string.rep('c',32),sector='sector_one',timeout=10,
 clock=function()return now end,guard=function()return opts.guard~=false,game end,
 count=function()return n end,issue=function(screen,op,args)
  items[#items+1]={screen=screen,op=op,args=args};if op=='Create' then n=11 end;return not opts.issue_fail end,
 snapshot=function()if opts.snapshot_fail then error('bad snapshot') end;return {x=opts.x or -399.125,y=100000,z=500.25,actor_key=opts.actor or '10',sector_key='11'} end,
 emit_descriptor=function(v)out[#out+1]=v;if opts.on_emit then opts.on_emit() end;return not opts.emit_fail end,
 inspect_complete=function(v)complete[#complete+1]=v;if opts.on_complete then opts.on_complete() end;return not opts.complete_fail end}
 local d=assert(M.new(settings));local function init()
  assert(d:start());assert(d:event(registry..'.Initialized',settings.epoch))
 end
 return d,init,items,out,complete,settings
end
local function finish(d,s)
 assert(d:event(registry..'.Created',3));assert(d:event(inspect..'.Result',s.nonce..'-1|'..s.epoch..'|0x01|0x02|sector_one'));assert(d:event(registry..'.Created',3))
 return d:event(inspect..'.Result',s.nonce..'-2|'..s.epoch..'|0x01|0x02|sector_one')
end
local source,init,ops,out,_,s=setup('source');init();assert(finish(source,s));assert(source:state()=='await_ack');assert(#out==1)
local wire=out[1];assert(wire.x==-399.125 and wire.z==500.25 and wire.actor==nil and wire.sector_handle==nil)
local client,initc,cops,_,completed,cs=setup('client');initc();assert(client:state()=='await_descriptor')
assert(client:accept_descriptor(wire));assert(cops[#cops].args.x==wire.x);assert(finish(client,cs));assert(client:state()=='done' and #completed==1)
assert(source:confirm_ack(completed[1]));assert(source:state()=='done')
assert(not source:event(registry..'.Created',3));assert(source:state()=='failed')
for _,field in ipairs({'attempt','epoch','sequence','index','macro','sector','owner','seed','x'}) do
 local c,ic=setup('client');ic();local invalid={};for k,v in pairs(wire) do invalid[k]=v end
 invalid[field]=field=='x' and 0/0 or 'wrong';assert(not c:accept_descriptor(invalid));assert(c:state()=='failed')
end
local c,ic=setup('client');ic();local extra={};for k,v in pairs(wire) do extra[k]=v end;extra.actor='0x1';assert(not c:accept_descriptor(extra))
local f,iff,_,_,fc,fs=setup('client',{snapshot_fail=true});iff();assert(f:accept_descriptor(wire));assert(f:event(registry..'.Created',3));assert(not f:event(inspect..'.Result',fs.nonce..'-1|'..fs.epoch..'|0x01|0x02|sector_one'));assert(#fc==0)
local x,ix,_,xo,_,xs=setup('source',{emit_fail=true});ix();assert(not finish(x,xs));assert(#xo==1 and x:state()=='failed')
local slow,is=setup('source');is();now=12;assert(not slow:tick());assert(slow:state()=='failed');now=1
local bad,ib=setup('client',{guard=false});assert(not bad:start());assert(bad:state()=='failed')
local mismatch,im,_,_,mc,ms=setup('client');im();assert(mismatch:accept_descriptor(wire));assert(mismatch:event(registry..'.Created',3));assert(not mismatch:event(inspect..'.Result',ms.nonce..'-1|'..ms.epoch..'|0x01|0x02|foreign'));assert(#mc==0)
local far,ifv,_,_,far_complete,fars=setup('client',{x=wire.x+2.01});ifv();assert(far:accept_descriptor(wire));assert(far:event(registry..'.Created',3));assert(not far:event(inspect..'.Result',fars.nonce..'-1|'..fars.epoch..'|0x01|0x02|sector_one'));assert(#far_complete==0)
local bound,ibound,_,_,bound_complete,bounds=setup('client',{x=wire.x+2});ibound();assert(bound:accept_descriptor(wire));assert(finish(bound,bounds));assert(#bound_complete==1)
local changed={};local change,ichange,_,_,change_complete,changes=setup('client',changed);ichange();assert(change:accept_descriptor(wire));assert(change:event(registry..'.Created',3));assert(change:event(inspect..'.Result',changes.nonce..'-1|'..changes.epoch..'|0x01|0x02|sector_one'));changed.actor='12';assert(change:event(registry..'.Created',3));assert(not change:event(inspect..'.Result',changes.nonce..'-2|'..changes.epoch..'|0x01|0x02|sector_one'));assert(#change_complete==0)
local reenter={};local rd,ri,_,_,_,rs=setup('source',reenter);reenter.on_emit=function() assert(not rd:tick()) end;ri();assert(not finish(rd,rs));assert(rd:state()=='failed')
local delayed={};local dd,di,_,_,_,ds=setup('source',delayed);delayed.on_emit=function() now=12 end;di();assert(not finish(dd,ds));assert(dd:state()=='failed');now=1
local pauseopts={};local pd,pi,_,_,pc,ps=setup('client',pauseopts);pauseopts.on_complete=function()pauseopts.guard=false end;pi();assert(pd:accept_descriptor(wire));assert(not finish(pd,ps));assert(pd:state()=='failed' and #pc==1)
local lateopts={};local ld,li,_,_,lc,ls=setup('client',lateopts);lateopts.on_complete=function()now=12 end;li();assert(ld:accept_descriptor(wire));assert(not finish(ld,ls));assert(ld:state()=='failed' and #lc==1);now=1
local terminalopts={};local td,ti,_,_,_,ts=setup('client',terminalopts);ti();assert(td:accept_descriptor(wire));assert(finish(td,ts));assert(td:tick());terminalopts.guard=false;assert(not td:tick());assert(td:state()=='failed')
print('ok')
