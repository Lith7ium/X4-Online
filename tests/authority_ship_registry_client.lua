-- Synthetic adapter contract only: no game engine, network, or cross-instance claims.
local registry = assert(loadfile('src/authority/lua/ship_registry_client.lua'))()
local function fixture(overrides)
 local t, sent, completed = 0, {}, {}
 local opts = {
  enabled = true, epoch = string.rep('a', 32), timeout = 2,
  clock = function() return t end,
  issue = function(screen, control, params)
   sent[#sent + 1] = { screen = screen, control = control, params = params }
   return true
  end,
  valid = function(actor) return actor == 'local-ship' end,
  key = function(actor) assert(actor == 'local-ship' or actor == 'md-actor'); return 'local-key' end,
  to_md_actor = function(actor, key)
   assert(actor == 'local-ship' and key == 'local-key'); return 'md-actor'
  end,
  complete = function(op, value) completed[#completed + 1] = {op, value}; return true end,
 }
 for k,v in pairs(overrides or {}) do opts[k] = v end
 local c = assert(registry.new(opts))
 return c, sent, completed, function(v) t = v end
end
local function expect_request(sent, i, control)
 local request = assert(sent[i])
 assert(request.screen == 'X4AuthorityShipRegistry' and request.control == control)
 return request.params
end
local function expect_failed(c)
 assert(c:state() == 'failed')
 assert(not c:status())
end

-- Initialize, two-event status and registration/lookup, with exactly one pending request.
do
 local c, sent, done = fixture()
 assert(c:state() == 'idle')
 assert(c:initialize())
 assert(expect_request(sent, 1, 'Initialize').epoch == string.rep('a', 32))
 assert(c:state() == 'pending')
 c:on_event('Initialized', string.rep('a', 32))
 assert(c:state() == 'idle' and done[1][1] == 'Initialize')
 assert(c:status())
 expect_request(sent, 2, 'Status')
 c:on_event('Epoch', string.rep('a', 32))
 assert(c:state() == 'pending' and #done == 1)
 c:on_event('Count', 8)
 assert(c:state() == 'idle' and done[2][1] == 'Status')
 assert(done[2][2].epoch == string.rep('a', 32) and done[2][2].count == 8)
 assert(c:enroll('local-ship'))
 local req = expect_request(sent, 3, 'Enroll')
 assert(req.epoch == string.rep('a', 32) and req.ship == 'md-actor')
 c:on_event('Enrolled', 9)
 assert(c:state() == 'idle' and done[3][1] == 'Enroll' and done[3][2] == 9)
 assert(c:resolve(9))
 req = expect_request(sent, 4, 'Resolve')
 assert(req.epoch == string.rep('a', 32) and req.index == 9)
 c:on_event('Actor', 'local-ship')
 assert(c:state() == 'idle' and done[4][1] == 'Resolve' and done[4][2] == 'local-ship')
 c:close()
 assert(c:state() == 'closed' and not c:status())
end

-- Out-of-order, unsolicited and late replies cannot be accepted as completions.
do
 local c, _, done = fixture()
 assert(c:status())
 c:on_event('Count', 1)
 expect_failed(c); assert(#done == 0)
end
do
 local c, _, done = fixture()
 c:on_event('Enrolled', 1)
 expect_failed(c); assert(#done == 0)
end
do
 local c, _, done, set_time = fixture()
 assert(c:resolve(2)); set_time(3); c:tick()
 expect_failed(c)
 c:on_event('Actor', 'local-ship')
 expect_failed(c); assert(#done == 0)
end
-- A reply naming a different epoch cannot confirm this registry.
do
 local c, _, done = fixture()
 assert(c:status()); c:on_event('Epoch', 'wrong-epoch')
 expect_failed(c); assert(#done == 0)
end
-- MD explicit refusal and dispatch/callback failures never produce completion.
do
 local c, _, done = fixture()
 assert(c:enroll('local-ship')); c:on_event('Refused')
 expect_failed(c); assert(#done == 0)
end
do
 local c, _, done = fixture({issue = function() error('dispatch failure') end})
 pcall(function() c:status() end)
 expect_failed(c); assert(#done == 0)
end
do
 local c = fixture({complete = function() error('callback failure') end})
 assert(c:initialize())
 pcall(function() c:on_event('Initialized', string.rep('a', 32)) end)
 expect_failed(c)
end
-- Actor identity must survive conversion and remain valid until the answer.
do
 local c, _, done = fixture({key=function(actor)
  return actor=='md-actor' and 'wrong-key' or 'local-key'
 end})
 assert(not c:enroll('local-ship'))
 expect_failed(c); assert(#done==0)
end
do
 local alive=true
 local c, _, done = fixture({valid=function(actor) return alive and actor=='local-ship' end})
 assert(c:enroll('local-ship'));alive=false
 assert(not c:on_event('Enrolled', 1))
 expect_failed(c);assert(#done==0)
end
-- A response at the deadline is too late even if tick was never called.
do
 local c, _, done, set_time = fixture()
 assert(c:resolve(1));set_time(2)
 assert(not c:on_event('Actor', 'local-ship'))
 expect_failed(c);assert(#done==0)
end
-- A response delivered synchronously from issue is not an accepted completion.
do
 local c, sent, done
 c, sent, done = fixture({issue=function() c:on_event('Epoch',string.rep('a',32));return true end})
 assert(not c:status());expect_failed(c);assert(#done==0)
end
-- None of the injected callbacks can close the client and then cause a
-- successful dispatch or completion by returning an otherwise valid value.
do
 local c, sent, done
 c, sent, done=fixture({clock=function() c:close();return 0 end})
 assert(not c:initialize() and c:state()=='closed' and #sent==0 and #done==0)
end
do
 local c, sent, done
 c, sent, done=fixture({valid=function() c:close();return true end})
 assert(not c:enroll('local-ship') and c:state()=='closed' and #sent==0 and #done==0)
end
do
 local c, sent, done
 c, sent, done=fixture({to_md_actor=function() c:close();return 'md-actor' end})
 assert(not c:enroll('local-ship') and c:state()=='closed' and #sent==0 and #done==0)
end
do
 local c, sent, done
 c, sent, done=fixture({issue=function() c:close();return true end})
 assert(not c:initialize() and c:state()=='closed' and #done==0)
end
do
 local c, sent, done;local close_now=false
 c, sent, done=fixture({valid=function() if close_now then c:close() end;return true end})
 assert(c:enroll('local-ship'));close_now=true
 assert(not c:on_event('Enrolled',1) and c:state()=='closed' and #done==0)
end
do
 local c, sent, done
 c, sent, done=fixture({to_md_actor=function() c:close();return 'md-actor' end})
 assert(c:resolve(1))
 assert(not c:on_event('Actor','local-ship') and c:state()=='closed' and #done==0)
end
do
 local c, sent, done
 c, sent, done=fixture({key=function() c:close();return 'local-key' end})
 assert(not c:enroll('local-ship') and c:state()=='closed' and #sent==0 and #done==0)
end
do
 local c, sent, done
 c, sent, done=fixture({clock=function() c:tick();return 0 end})
 assert(not c:initialize());expect_failed(c);assert(#sent==0 and #done==0)
end
-- Slow injected calls cannot turn an expired operation into a success.
do
 local c, sent, done, set_time
 c, sent, done, set_time=fixture({issue=function() set_time(2);return true end})
 assert(not c:initialize());expect_failed(c);assert(#done==0)
end
do
 local c, sent, done, set_time
 c, sent, done, set_time=fixture({valid=function() set_time(2);return true end})
 assert(c:resolve(1))
 assert(not c:on_event('Actor','local-ship'));expect_failed(c);assert(#done==0)
end
do
 local c, sent, done, set_time
 c, sent, done, set_time=fixture({to_md_actor=function() set_time(2);return 'md-actor' end})
 assert(c:resolve(1))
 assert(not c:on_event('Actor','local-ship'));expect_failed(c);assert(#done==0)
end
do
 local c, sent, done, set_time
 c, sent, done, set_time=fixture({key=function() set_time(2);return 'local-key' end})
 assert(c:resolve(1))
 assert(not c:on_event('Actor','local-ship'));expect_failed(c);assert(#done==0)
end
do
 local c, sent, done, set_time;local callback_called=false
 c, sent, done, set_time=fixture({complete=function() callback_called=true;set_time(2);return true end})
 assert(c:initialize())
 assert(not c:on_event('Initialized',string.rep('a',32)))
 expect_failed(c);assert(callback_called)
end
-- A conflicting call while a request is pending fails closed.
do
 local c = fixture()
 assert(c:status())
 assert(not c:resolve(1))
 expect_failed(c)
end
-- Without request IDs, an old same-kind reply arriving during a new request
-- is indistinguishable from a current reply. This documents the limitation.
do
 local c, _, done = fixture()
 assert(c:resolve(1)); c:on_event('Actor', 'local-ship')
 assert(c:resolve(2)); c:on_event('Actor', 'local-ship') -- could be stale
 assert(c:state() == 'idle' and #done == 2 and done[2][2] == 'local-ship')
end

-- Optional correlated responses retain exact 64-bit actor IDs as text and
-- must reject an old response even when its type matches a later request.
do
 local nonce=string.rep('b',32)
 local actor='local-actor'; local actor_id='18446744073709551615'; local actor_hex='0xffffffffffffffff'
 local c,sent,done=fixture({correlation_nonce=nonce,
  valid=function(v) return v==actor end,
  key=function(v) if v==actor or v=='md-actor' then return actor_id end end,
  to_md_actor=function(v,k) assert(v==actor and k==actor_id);return 'md-actor' end,
  from_md_actor=function(s) assert(s==actor_hex);return actor end})
 assert(c:initialize());assert(sent[1].params.request_id==nonce..':1')
 assert(c:on_event('Correlated',nonce..':1|Initialized|'..string.rep('a',32)))
 assert(c:status());assert(sent[2].params.request_id==nonce..':2')
 assert(c:on_event('Correlated',nonce..':2|Epoch|'..string.rep('a',32)))
 assert(c:on_event('Correlated',nonce..':2|Count|4'))
 assert(done[2][2].count==4)
 assert(c:enroll(actor));assert(c:on_event('Correlated',nonce..':3|Enrolled|5'))
 assert(done[3][2]==5)
 assert(c:resolve(5));assert(c:on_event('Correlated',nonce..':4|Actor|'..actor_hex))
 assert(done[4][2]==actor)
 assert(c:resolve(6))
 assert(not c:on_event('Correlated',nonce..':4|Actor|'..actor_hex))
 expect_failed(c);assert(#done==4)
end
-- Uncorrelated replies cannot complete a correlated request, and a malformed
-- numeric representation must not be silently rounded to a Lua number.
do
 local c,_,done=fixture({correlation_nonce=string.rep('b',32),from_md_actor=function() end})
 assert(c:enroll('local-ship'));assert(not c:on_event('Enrolled',1));expect_failed(c);assert(#done==0)
end
do
 local n=string.rep('c',32)
 local c,_,done=fixture({correlation_nonce=n,from_md_actor=function() end})
 assert(c:enroll('local-ship'))
 assert(not c:on_event('Correlated',n..':1|Enrolled|9007199254740992'));expect_failed(c);assert(#done==0)
end

-- Correlation must precede actor conversion; stale replies cannot even invoke
-- a caller's converter, and mismatched conversion keys cannot be accepted.
do
 local n=string.rep('d',32);local conversions=0
 local c,_,done=fixture({correlation_nonce=n,from_md_actor=function() conversions=conversions+1;return 'local-ship' end})
 assert(c:resolve(1))
 assert(not c:on_event('Correlated',n..':2|Actor|0x7b'))
 expect_failed(c);assert(conversions==0 and #done==0)
end
do
 local n=string.rep('e',32)
 local c,_,done=fixture({correlation_nonce=n,from_md_actor=function() return 'local-ship' end})
 assert(c:resolve(1))
 assert(not c:on_event('Correlated',n..':1|Actor|0x7b'))
 expect_failed(c);assert(#done==0)
end
-- Hex parsing is bounded to the uint64 domain, rejects zero and accepts both
-- cases and leading zeroes without precision loss.
for _,pair in ipairs({{'0x1','1'}, {'0X0000200000000001','35184372088833'},
                      {'0x20000000000001','9007199254740993'},
                      {'0xFFFFFFFFFFFFFFFF','18446744073709551615'}}) do
 local n=string.rep('f',32);local actor='local-actor'
 local c,_,done=fixture({correlation_nonce=n,from_md_actor=function() return actor end,
  valid=function(v) return v==actor end,
  key=function(v) if v==actor or v=='md-actor' then return pair[2] end end,
  to_md_actor=function() return 'md-actor' end})
 assert(c:resolve(1));assert(c:on_event('Correlated',n..':1|Actor|'..pair[1]))
 assert(#done==1 and done[1][2]==actor)
end
for _,bad in ipairs({'0x0','0x0000','0x10000000000000000','123','0x','0xg'}) do
 local n=string.rep('f',32);local conversions=0
 local c,_,done=fixture({correlation_nonce=n,from_md_actor=function() conversions=conversions+1 end})
 assert(c:resolve(1));assert(not c:on_event('Correlated',n..':1|Actor|'..bad))
 expect_failed(c);assert(#done==0 and conversions==0)
end
-- A correctly correlated wrong-kind event must not invoke actor conversion.
do
 local n=string.rep('f',32);local conversions=0
 local c,_,done=fixture({correlation_nonce=n,from_md_actor=function() conversions=conversions+1 end})
 assert(c:status());assert(not c:on_event('Correlated',n..':1|Actor|0x1'))
 expect_failed(c);assert(conversions==0 and #done==0)
end
print('synthetic ship registry client contract passed')
