local M=dofile('src/authority/lua/recovery_registry_status.lua')
local now=1;local callback;local issued={};local logged={};local stored={};local paused=true
local owner=M.new({nonce=string.rep('a',32),expected=string.rep('c',32)..'|17',clock=function()return now end,paused=function()return paused end,
 register=function(f)callback=f;return true end,
 issue=function(screen,op,args)issued[#issued+1]={screen,op,args.request_id};return true end,
 log=function(marker,status)logged[#logged+1]={marker,status};return true end,
 store=function(marker)stored[#stored+1]=marker;return true end})
assert(owner:begin());local r=issued[1][3];assert(not owner:ready())
callback(nil,r..'|Epoch|'..string.rep('c',32));callback(nil,r..'|Count|17');assert(owner:ready())
local marker=string.rep('b',32);assert(owner:begin(marker));r=issued[2][3]
callback(nil,r..'|Epoch|'..string.rep('c',32));assert(not owner:ready() and #stored==0)
callback(nil,r..'|Count|17');assert(owner:ready() and stored[1]==marker and logged[2][2]==string.rep('c',32)..'|17')
assert(owner:begin());assert(not pcall(callback,nil,r..'|Count|17'));assert(not owner:tick())
local function fresh()
 local cb;local request;local paused=true;local t=1
 local obj=M.new({nonce=string.rep('d',32),expected='uninitialized',clock=function()return t end,paused=function()return paused end,
  register=function(f)cb=f;return true end,issue=function(_,_,args)request=args.request_id;return true end,
  log=function()return true end,store=function()error('must not store')end})
 assert(obj:begin())
 return obj,function(value)cb(nil,request..value)end,function()paused=false end,function()t=50 end
end
local pending,event,unpause,expire=fresh();unpause();assert(not pending:tick())
pending,event,unpause,expire=fresh();expire();assert(not pending:tick())
pending,event=fresh();assert(not pcall(event,'|Faulted|'));assert(not pending:tick())
pending,event=fresh();assert(not pcall(event,'|Count|1'));assert(not pending:tick())
pending,event=fresh();event('|Uninitialized|');assert(pending:ready())
pending,event=fresh();event('|Epoch|'..string.rep('c',32));assert(not pcall(event,'|Count|17'));assert(not pending:tick())
local nested
local reentrant=M.new({nonce=string.rep('e',32),expected='uninitialized',clock=function()return 1 end,paused=function()return true end,
 register=function(f)nested=f;return true end,
 issue=function(_,_,args)pcall(nested,nil,args.request_id..'|Uninitialized|');return true end,
 log=function()error('must not log')end,store=function()error('must not store')end})
assert(not reentrant:begin());assert(not reentrant:tick())
print('recovery registry status checks passed')
-- Fault callback is optional and called exactly once, including a late reply.
do
 local cb, faults;faults=0
 local obj=M.new({nonce=string.rep('f',32),expected='uninitialized',clock=function()return 1 end,paused=function()return true end,
  register=function(f)cb=f;return true end,issue=function()return true end,log=function()return true end,store=function()return true end,
  fault=function()faults=faults+1 end})
 assert(obj:begin());cb(nil,string.rep('f',32)..':1|Uninitialized|');assert(obj:ready())
 assert(obj:expect_bootstrap(string.rep('a',32),2));assert(not obj:expect_bootstrap(string.rep('a',32),2))
 assert(faults==1);assert(not obj:tick() and faults==1)
end
-- A stale response after a completed barrier is reported exactly once.
do
 local cb;local faults=0;local nonce=string.rep('9',32)
 local obj=M.new({nonce=nonce,expected='uninitialized',clock=function()return 1 end,paused=function()return true end,
  register=function(f)cb=f;return true end,issue=function()return true end,log=function()return true end,store=function()return true end,
  fault=function()faults=faults+1 end})
 assert(obj:begin());cb(nil,nonce..':1|Uninitialized|');assert(obj:ready())
 assert(not pcall(cb,nil,nonce..':1|Uninitialized|'));assert(faults==1 and not obj:tick())
 assert(not pcall(cb,nil,nonce..':1|Uninitialized|'));assert(faults==1)
end
-- A completed status observation is inert during resume, but cannot start a
-- fresh marker observation until the world is paused again.
do
 local cb;local paused=true;local nonce=string.rep('8',32)
 local obj=M.new({nonce=nonce,expected='uninitialized',clock=function()return 1 end,
  paused=function()return paused end,register=function(f)cb=f;return true end,
  issue=function()return true end,log=function()return true end,store=function()return true end})
 assert(obj:begin());cb(nil,nonce..':1|Uninitialized|');assert(obj:ready())
 paused=false;assert(obj:tick() and obj:ready())
 assert(not obj:begin(string.rep('a',32)) and not obj:tick())
end
