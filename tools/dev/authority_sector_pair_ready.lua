-- Default-off read-only two-process readiness; load probe owns onUpdate.
local cfg=X4LAN_CONFIG
if not cfg or cfg.authority_sector_pair_ready~=true then return end
local ffi=require('ffi');local C=ffi.C
local epoch,nonce,role=cfg.authority_sector_epoch,cfg.authority_pair_nonce,cfg.authority_pair_role
local macros=cfg.authority_pair_macros
assert(type(nonce)=='string' and #nonce==32 and nonce:match('^[0-9a-f]+$'))
assert(role=='server' or role=='client')
assert(type(macros)=='table' and #macros==2 and macros[1]~=macros[2])
for _,v in ipairs(macros) do assert(type(v)=='string' and #v<=128 and v:match('^[%w_%-%.]+$')) end
local state='new';local failed=false;local t0,last,game0,deadline,a1,s1,a2,s2
local function log(s) DebugError('[X4LAN] AUTH_SECTOR_PAIR '..s) end
local function fail(s) if not failed then failed=true;state='failed';log('ERROR '..s) end end
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function guard()
 local path=C.GetSaveFolderPath()
 assert(path~=nil and path~=ffi.NULL and ffi.string(path):gsub('\\','/'):gsub('/+$','')==cfg.authority_read_save_path)
 assert(C.IsPlayerValid() and C.IsGamePaused())
 local t=GetCurRealTime();local game=tonumber(C.GetCurrentGameTime());local after=GetCurRealTime()
 assert(finite(t) and t>=0 and (not last or t>=last) and finite(game) and game>=0 and finite(after) and after>=t)
 last=after;t0=t0 or t;assert(after-t0<=cfg.authority_pair_deadline)
 if game0 then assert(game==game0) end
 return after,game
end
local function live(a,s)
 return C.IsValidComponent(a) and C.IsComponentOperational(a) and C.IsComponentClass(a,'ship') and
  C.IsValidComponent(s) and C.IsComponentClass(s,'sector') and C.GetContextByClass(a,'sector',false)==s
end
RegisterEvent('X4AuthoritySectorPairReady.Refused',function()fail('refused')end)
RegisterEvent('X4AuthoritySectorPairReady.Result',function(_,value)
 if failed then return end
 local ok=pcall(function()
  local t,game=guard();assert(state=='waiting' and t<=deadline and game==game0 and type(value)=='string' and #value<=700)
  local id,ep,ah,sh,bh,th,m1,m2=value:match('^([0-9a-f]+)|([0-9a-f]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|(0[xX][0-9a-fA-F]+)|([%w_%-%.]+)|([%w_%-%.]+)$')
  assert(id==nonce and ep==epoch and m1==macros[1] and m2==macros[2])
  a1=X4LAN_RESOLVE_STRING.parse_hex(ah);s1=X4LAN_RESOLVE_STRING.parse_hex(sh)
  a2=X4LAN_RESOLVE_STRING.parse_hex(bh);s2=X4LAN_RESOLVE_STRING.parse_hex(th)
  assert(a1 and s1 and a2 and s2 and a1~=a2 and s1~=s2 and live(a1,s1) and live(a2,s2))
  local initial_actor,initial_sector,_,initial_game=X4LAN_SECTOR_READ_EXPORT()
  assert(a2==initial_actor and s2==initial_sector and initial_game==game)
  local checked,after=guard();assert(checked<=deadline and after==game and live(a1,s1) and live(a2,s2))
  local final,final_game=guard();assert(final<=deadline and final_game==game)
  state='done';log(('READY role=%s nonce=%s game=%.17g'):format(role,nonce,game))
 end)
 if not ok then fail('result') end
end)
function X4LAN_SECTOR_PAIR_TICK()
 if failed then error('pair readiness failed') end
 local ok=pcall(function()
  local t,game=guard()
  if state=='new' then
   local _,_,_,initial_game=X4LAN_SECTOR_READ_EXPORT();assert(initial_game==game)
   game0=game;deadline=t+10;state='waiting'
   assert(AddUITriggeredEvent('X4AuthoritySectorPairReady','Read',{epoch=epoch,request_id=nonce})~=false)
   local after,after_game=guard();assert(not failed and after<=deadline and after_game==game0)
  elseif state=='waiting' then assert(t<=deadline)
  elseif state=='done' then assert(live(a1,s1) and live(a2,s2))
  else error('invalid state') end
 end)
 if not ok then fail('state');error('pair readiness failed') end
 return state=='done'
end
