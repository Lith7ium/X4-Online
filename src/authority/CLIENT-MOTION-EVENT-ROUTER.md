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
`replica_motion_binding.new_x4` accepts an explicit `md_issue` function;
`motion_client_owner.new_x4` can explicitly receive `event_router` and
`router_generation`, delegate Bind events to that router and check that its
own nonce, registry epoch and local generation remain the active association.
The default owners still reserve/register their own listeners, and a module
incarnation refuses mixing the default and externally routed modes. The
recovered-session installer selects the read-only Bind routes. A separate,
explicit `saved_apply=true` router option can also register the saved-position
Inspect event for an isolated setter experiment. This option requires a bounded
`max_apply_requests` and an owner with an `apply_event` method; it is not enabled
by the recovered-session installer and does not itself enable the setter.

The outer owner supplies fresh, distinct 128-bit local generation and request
nonce values for each activation, and the unchanged saved-registry epoch. It
attaches a newly created owner before starting it, or a ready generic owner.
The caller must fail the enclosing session if starting an attached owner fails.
The guard must independently fence the actual
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

When the optional Inspect route is enabled, `saved_motion_apply.new_x4`
receives the router's issue callback and the full owner nonce. Its MD request
ID is `<owner nonce>-<operation token>-pre` or `-post`; the writer and router
both check the exact response. The router pins `apply_event` along with the
other owner methods, permits one outstanding request across all routes, and
bounds remembered operation tokens for the owner. `post` requires a previous
`pre` from the same applying operation and the same local references; a
preflight operation cannot authorize a later post. A refused response, stale
nonce, duplicate request or event, changed method, wrong owner state, uncertain
dispatch or guard failure fences the router. A possible game-side write is not
retried or rolled back. An accepted Inspect response remains a local callback;
it is not evidence of sustained position control.

Reference equality here is intentionally conservative. The X4 converter can
return userdata, and it has not been established that separately converted
wrappers for the same native identity compare equal. Such wrappers can make a
legitimate post inspection fail closed. The router rejects table references,
but compares cdata and userdata shallowly; it relies on the cooperative X4
adapter to supply valid local handles and not mutate their contents. The fake ABI test uses cdata and does
not settle actual X4 behavior; no native run has checked the longer request ID,
third-route serialization or delayed post. The existing one-ship fixture,
profile, position, player, sector and process guards are unchanged. This route
does not establish authority transfer, collision clearance, Windows, internet,
or gameplay.

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

`tests/authority_client_motion_apply_router.lua` exercises the optional route,
replays, stale generations, method changes and fencing.
`tests/authority_client_motion_apply_router_x4.lua` composes the real Lua owner,
binder and writer with a fake X4 ABI and simulated MD; no X4 process is run.
`tests/authority_client_motion_event_router.lua` exercises routing, bounded
state, stale and unknown callbacks, STOP fences and reentrancy with simulated
owners and callbacks. `tests/authority_client_motion_router_x4.lua` composes
the router with actual local Lua motion owners and saved/replica binders, using
fake X4 ABI and simulated MD, and rotates the local owner and nonce after STOP.
The separate `tools/dev/authority_recovered_client_motion_install.py` prepares
an additive, read-only, one-shot diagnostic overlay and secret redaction. Its
Lua and installer tests use a simulated X4 environment. The supervisor still
must install and protect that overlay, hand off the separate UDP FD exclusively,
monitor errors through pause and cleanup, and fence STOP before allowing pause.
The one-shot lease cannot resume after a subsequent join pause.
The private overlay can instead receive a bounded list of saved indices. It
latches the first correlated BIND to a member of that list and refuses a later
index change; the host must still send only the source-selected index. Matching
indices remain an experimental saved-reference assumption, not evidence of
cross-process ship identity.

No X4 process, real MD serialization, FD handoff, Windows, internet, visible
motion or gameplay is covered by these router and installer tests.
