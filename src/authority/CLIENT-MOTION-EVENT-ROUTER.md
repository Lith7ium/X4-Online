# Experimental permanent client motion event router

`lua/client_motion_event_router.lua` is default-off and owns no X4 hook or
socket until an explicit caller supplies and invokes `start()`. It is an
isolated local building block, not wired into the current client session. Its
`new_x4` factory claims registration once for that Lua module incarnation;
the installer must also prevent the module from being loaded more than once.
Failed or partial registration does not release that claim. The generic `new`
factory relies on its caller to provide exclusive registration.
The caller must register the two event names exactly once for one process/load
incarnation, retain exclusive control of registration and the X4 update loop,
and route the local binder's `AddUITriggeredEvent` call through `issue`.
The existing `replica_motion_binding.new_x4` does not yet support an injected
issuer, and `motion_client_owner.new_x4` reserves its own event registration;
there is therefore no existing native caller of this router.

The outer owner supplies fresh, distinct 128-bit local generation and request
nonce values for each activation, and the unchanged saved-registry epoch. It
attaches only a ready owner. The guard must independently fence the actual
process, profile, checkpoint/load incarnation and association among owner,
generation, nonce and registry epoch; these arguments are assertions supplied
to the callback, not self-authenticating evidence. Router generation is local:
it is not a ship lifetime, session epoch, or a substitute for the user's
approved persistent ship-generation scheme.

Only one read-only Bind request can be outstanding. Its full nonce/index/counter
and route must match the response before delivery. The router checks per-index
counter advancement, argument shape, callback return values and provisional
owner state after the callback. It fails permanently on unexpected, duplicate,
late, wrong-route or wrong-generation replies, guard loss, owner reentrancy,
uncertain dispatch or callback failure. It never retries or invents a receipt.
Unknown and retired responses are not routed to the new owner. A sender's
return and these checks are non-atomic; process and owner failure must fence the
entire experimental session.

The owner can be retired only with no outstanding request, local owner state
`stopped`, and a successful caller-provided `retire_guard` that checks the real
STOPPED handshake and its surrounding fences. A generation/nonce is never
reused or evicted; configured generation and track limits make exhaustion a
fault rather than an implicit safe timeout. The router's handling of one late
reply does not prove no other message can arrive later. It must remain the
exclusive event owner throughout and the encompassing X4 session must propagate
its fault to the supervisor, even during a game pause. Transport lease rotation,
TCP motion barrier/drain, FD handoff, stopped-owner cleanup, reactivation and
cross-process ship/frame identity remain separate requirements.

`tests/authority_client_motion_event_router.lua` exercises routing, bounded
state, stale and unknown callbacks, STOP fences and reentrancy with simulated
owners and callbacks. No X4 process, real MD serialization, FD handoff, Windows,
internet, visible motion or gameplay is covered.
