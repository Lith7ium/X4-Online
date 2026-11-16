-- Explicit private X4 binding. Installs no onUpdate; caller owns the only tick.
local M={}
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(type(c.owner)=='table' and type(c.owner.new)=='function' and type(c.guard)=='function')
 assert(type(c.host)=='table' and type(c.probe)=='table' and type(c.descriptor)=='table' and type(c.descriptor_core)=='table' and type(c.witness)=='table')
 assert(type(c.expected_save_path)=='string' and c.expected_save_path:sub(1,1)=='/' and c.expected_save_path:sub(-11)=='/45841/save')
 assert(type(c.port)=='number' and c.port%1==0 and c.port>=1 and c.port<=65535 and type(c.window)=='number' and c.window>=1 and c.window<=180)
 for _,k in ipairs({'RegisterEvent','AddUITriggeredEvent','GetCurRealTime','Pause','Unpause','DebugError'})do assert(type(_G[k])=='function')end
 local ffi=require('ffi');ffi.cdef[[bool IsGamePaused(void);bool IsPlayerValid(void);double GetCurrentGameTime(void);const char* GetSaveFolderPath(void);]];local C=ffi.C
 local lib=assert(package.loadlib('./extensions/x4_lan_lab/native/x4lan_net.so','luaopen_x4lan_net'))();local net=assert(lib.open('127.0.0.1',c.port));local owner
 local function guard()
  local p=C.GetSaveFolderPath()
  return c.guard()==true and p~=nil and p~=ffi.NULL and ffi.string(p):gsub('\\','/'):gsub('/+$','')==c.expected_save_path and C.IsPlayerValid()
 end
 local ok,err=pcall(function()
  owner=assert(c.owner.new({enabled=true,role=c.role,epoch=c.epoch,attempt=c.attempt,lease=c.lease,nonce=c.nonce,timeout=c.timeout,window=c.window,net=net,
   clock=GetCurRealTime,guard=guard,observe=function()return C.IsGamePaused(),tonumber(C.GetCurrentGameTime())end,pause=Pause,resume=Unpause,
   baseline_request=function(epoch,request_id)return AddUITriggeredEvent('X4AuthorityCensusJobBaseline','Read',{epoch=epoch,request_id=request_id})~=false end,
   log=function(v)DebugError('[X4LAN] AUTH_CENSUS_JOB '..(v=='FAULT' and 'ERROR FAULT' or v))end,
   host_factory=function(report,fault,no_event)
    return assert(c.host.new_x4({enabled=true,epoch=c.epoch,baseline={},expose_actor=true,attach_saved_registry=true,exclusive_registry_consumer=true,
     expected_last=10054,expected_save_path=c.expected_save_path,capacity=128,window=c.window,timeout=10,probe=c.probe,
     report=report,done=no_event,fault=fault}))
   end,
   descriptor_factory=function(row,actor)
    return assert(c.descriptor.new_x4({enabled=true,core=c.descriptor_core,epoch=c.epoch,request_id=c.nonce,timeout=5,row=row,actor=actor,
     expected_save_path=c.expected_save_path,guard=guard}))
   end,
   witness_factory=function(index,macro)
    return assert(c.witness.new_x4({enabled=true,epoch=c.epoch,request_id=c.nonce,index=index,macro=macro,timeout=5,
     expected_save_path=c.expected_save_path,guard=guard}))
   end}))
  assert(RegisterEvent('X4AuthorityPausedJobDescriptor.Result',function(_,v)owner:descriptor_event(v)end)~=false)
  assert(RegisterEvent('X4AuthoritySectorWitnessRuntime.Result',function(_,v)owner:witness_event(v)end)~=false)
  if c.role=='client' then assert(RegisterEvent('X4AuthorityCensusJobBaseline.Result',function(_,v)owner:baseline_event(v)end)~=false) end
 end)
 if not ok then pcall(net.close,net);error('census owner setup failed: '..tostring(err))end
 return owner
end
return M
