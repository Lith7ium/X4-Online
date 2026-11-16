local M=dofile('src/authority/lua/player_sector_interest.lua')
local epoch,inc,nonce=('a'):rep(32),('b'):rep(32),('c'):rep(32)
local now,good=1,true;local issued,out={},{};local app
local opt={enabled=true,epoch=epoch,incarnation=inc,nonce=nonce,timeout=5,clock=function()return now end,
 guard=function(i)assert(i==inc);return good end,
 issue=function(screen,op,args)assert(screen=='X4AuthorityPlayerSectorInterest' and op=='Read');issued[#issued+1]=args;return true end,
 inspect=function(hex,macro)if macro=='sector_a' and hex=='0x2b' then return '43' elseif macro=='sector_b' and hex=='0x2c' then return '44' elseif macro=='sector_a' and hex=='0x2d' then return '45' end end,
 complete=function(v)out[#out+1]=v;return true end}
app=assert(M.new(opt));assert(app:begin())
local function row(i,h,m)return issued[i].request_id..'|'..epoch..'|'..inc..'|ok|'..h..'|'..m end
assert(app:event(row(1,'0x2b','sector_a')) and #out==1 and out[1].sequence==1 and out[1].sector_macro=='sector_a')
assert(out[1].actor==nil and out[1].sector==nil and app:begin())
assert(app:event(row(2,'0x2c','sector_b')) and app:begin())
assert(not app:event(row(3,'0x2d','sector_a')) and app:state()=='failed')
app=assert(M.new(opt));assert(app:begin());assert(not app:event(row(4,'0x2b','sector_a')..'|extra'))
app=assert(M.new(opt));assert(app:begin());good=false;assert(not app:event(row(5,'0x2b','sector_a')));good=true
app=assert(M.new(opt));assert(app:begin());now=10;assert(not app:event(row(6,'0x2b','sector_a')));now=1
local reentrant={};for k,v in pairs(opt)do reentrant[k]=v end
reentrant.complete=function()app:tick();return true end
app=assert(M.new(reentrant));assert(app:begin());assert(not app:event(row(7,'0x2b','sector_a')))
local mutate={};for k,v in pairs(opt)do mutate[k]=v end
mutate.complete=function(v)v.extra=true;return true end
app=assert(M.new(mutate));assert(app:begin());assert(not app:event(row(8,'0x2b','sector_a')))
app=assert(M.new(opt));assert(app:begin());assert(not app:event(row(9,'0x2b','sector_a'):gsub(inc,epoch)))
print('player sector interest generic fences passed')
