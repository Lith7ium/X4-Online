-- Default-off source lifecycle gate. The caller owns the sole MD event hook,
-- process/profile fencing and transport. STOPPED is only meaningful after
-- stop() succeeds, and late events must still be delivered to event().
local M={}
function M.new(c)
 if type(c)~='table' or c.enabled~=true then return nil,'disabled' end
 assert(type(c.bootstrap)=='table' and type(c.bootstrap.state)=='function' and type(c.bootstrap.close)=='function')
 assert(type(c.sampler)=='table' and type(c.sampler.state)=='function' and type(c.sampler.close)=='function')
 for _,k in ipairs({'guard','quiescent','route','fault'})do assert(type(c[k])=='function',k..' required')end
 local state,busy='active',false;local api={}
 local function fail(reason)
  if state~='failed' then state='failed';pcall(c.fault,reason)end
  return false
 end
 local function guard(expected)
  local ok,value=pcall(c.guard)
  return ok and value==true and state==expected
 end
 local function quiet(expected)
  local ok,value=pcall(c.quiescent)
  return ok and value==true and state==expected
 end
 function api:event(value)
  if busy or state~='active' then return fail('late_or_reentrant_event')end
  busy=true
  local ok=pcall(function()
   assert(guard('active'))
   assert(c.route(value)==true and state=='active' and guard('active'))
  end)
  busy=false;if not ok then return fail('event')end;return true
 end
 function api:stop()
  if busy or state~='active' then return fail('stop_state')end
  busy=true;state='stopping'
  local ok=pcall(function()
   assert(guard('stopping') and quiet('stopping'))
   assert(c.bootstrap:state()=='idle' and c.sampler:state()=='ready')
   assert(guard('stopping') and quiet('stopping'))
   assert(c.bootstrap:close()==true and state=='stopping' and c.bootstrap:state()=='closed')
   assert(guard('stopping') and quiet('stopping'))
   assert(c.sampler:close()==true and state=='stopping' and c.sampler:state()=='closed')
   assert(guard('stopping') and quiet('stopping'))
   assert(c.bootstrap:state()=='closed' and c.sampler:state()=='closed' and state=='stopping')
   state='stopped'
  end)
  busy=false;if not ok then return fail('stop')end;return true
 end
 -- Call throughout the rest of the session, including after STOPPED.
 function api:check()
  if busy or (state~='active' and state~='stopped') then return fail('check_state')end
  local current=state;busy=true
  local ok=pcall(function()
   assert(guard(current))
   if current=='stopped' then
    assert(quiet('stopped') and c.bootstrap:state()=='closed' and c.sampler:state()=='closed' and state=='stopped')
   end
  end)
  busy=false;if not ok then return fail('check')end
  return true
 end
 function api:state()return state end
 return api
end
X4LAN_SOURCE_MOTION_SHUTDOWN=M
return M
