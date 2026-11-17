-- Private one-process measurement state machine; the caller owns its callbacks.
local M = {}
function M.new(callbacks, lease)
 assert(type(callbacks)=='table' and type(lease)=='string' and #lease==32 and lease:match('^[0-9a-f]+$'))
 local state, resume_nonce = 'ready', nil
 local function checked_clock()
  local value=callbacks.clock()
  assert(type(value)=='number' and value==value and value>=0 and value<math.huge, 'invalid game clock')
  return value
 end
 local function send(value) assert(callbacks.send(value)==true,'measurement send failed') end
 local function tick()
  assert(callbacks.valid(),'fixture context lost')
  if state=='ready' then
   assert(callbacks.paused(),'fixture lost initial pause')
   send('READY|'..lease);state='waiting';return
  end
  if state=='resuming' then
   if callbacks.paused() then return end
   local value=checked_clock();state='running'
   send(('RESUMED|%s|%s|%.17g'):format(lease,resume_nonce,value));return
  end
  assert(state~='running' or not callbacks.paused(),'fixture stopped running')
  local packet=callbacks.receive()
  if not packet then return end
  if state=='waiting' then
   assert(callbacks.paused(),'fixture lost initial pause')
   local nonce=packet:match('^RESUME|'..lease..'|([0-9a-f]+)$')
   assert(nonce and #nonce==32,'invalid resume request')
   resume_nonce=nonce;state='resuming';callbacks.unpause();return
  end
  assert(state=='running' and not callbacks.paused(),'fixture stopped running')
  local nonce=packet:match('^CLOCK|'..lease..'|([0-9a-f]+)$')
  assert(nonce and #nonce==32,'invalid clock request')
  send(('CLOCK_RESULT|%s|%s|%.17g'):format(lease,nonce,checked_clock()))
 end
 local failed=false
 return function()
  if failed then return false end
  local ok,err=pcall(tick)
  if not ok then failed=true;callbacks.error(tostring(err));return false end
  return true
 end
end
X4LAN_FIXTURE_SINGLE_MEASURE=M
return M
