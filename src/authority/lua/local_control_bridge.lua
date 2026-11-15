-- Inert factory. Caller owns an isolated profile, the UDP endpoint and the
-- event/update registrations. UDP loss faults the supervisor; no retransmit.
local M={}
function M.new(cfg,engine,net)
 if type(cfg)~='table' or cfg.enabled~=true then return nil,'disabled' end
 assert(type(cfg.lease)=='string' and #cfg.lease==32 and cfg.lease:match('^[0-9a-f]+$'))
 assert(type(cfg.world_epoch)=='string' and #cfg.world_epoch==32 and cfg.world_epoch:match('^[0-9a-f]+$'))
 assert(cfg.empty_owned_slot==true and net~=nil and type(net.send)=='function' and type(net.receive)=='function')
 local owner='isolated-supervisor';local epoch=cfg.world_epoch;local lease=cfg.lease
 local verified=false;local faulted=false;local state
 local function send(s) assert(net:send(s)==true,'control send failed') end
 local function report(row)
  if row.status=='failed' then faulted=true end
  send('RECEIPT|'..lease..'|'..epoch..'|'..string.format('%.0f',row.request_id)..'|'..row.operation..'|'..row.status)
 end
 state=assert(X4LAN_AUTHORITY_CONTROL_STATE.new({enabled=true,owner=owner,world_epoch=epoch,
  enable_verified_reuse=true,timeout_seconds=120},engine,report))
 local bridge={state=state}
 function bridge:update()
  if faulted then return false,'faulted' end
  for _=1,16 do
   local packet=net:receive();if not packet then break end
   local typ,l,e,id,op=packet:match('^([A-Z]+)|([0-9a-f]+)|([0-9a-f]+)|(%d+)|?([a-z]*)$')
   if l~=lease or e~=epoch or not id or #id>16 or id:match('^0') then faulted=true;return false,'packet' end
   local number=tonumber(id)
   if not number or number>9007199254740991 then faulted=true;return false,'request_id' end
   if typ=='CMD' and (op=='pause' or op=='save' or op=='resume') then
    local params=nil
    if op=='save' then
     params={slot='save_009',exclusive_owner=true}
     if verified then params.overwrite_verified_owned_slot=true else params.empty_owned_slot=true end
    end
    local ok,reason=state:submit(owner,epoch,number,op,params)
    if not ok then faulted=true;return false,reason end
   elseif typ=='VERIFY' and op=='' then
    local ok,reason=state:confirm_save(owner,epoch,number,true)
    if not ok then faulted=true;return false,reason end
    verified=true;send('VERIFIED|'..lease..'|'..epoch..'|'..id)
   else faulted=true;return false,'packet' end
  end
  local ok,reason=state:on_update()
  if not ok then faulted=true end
  return ok,reason
 end
 return bridge
end
X4LAN_AUTHORITY_LOCAL_CONTROL_BRIDGE=M
return M
