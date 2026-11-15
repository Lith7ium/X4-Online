# Experimental local ship registry client

`lua/ship_registry_client.lua` is an opt-in local integration primitive for
`tools/dev/authority_ship_registry.xml`. It installs nothing, performs no X4
calls on import, and does not provide networking or sector identity. The MD
registry itself remains experimental. This adapter has not been tested in X4.

Construct with `new({enabled=true, epoch=..., timeout=..., issue=..., key=...,
to_md_actor=..., valid=..., clock=..., complete=...})`. The epoch is 32 lowercase
hex characters. The injected clock is monotonic seconds and timeout is between
zero and 300 seconds. The caller owns X4 event registration and calls
`client:on_event(name, value)` with the short MD event name. It must call
`client:tick()` to enforce the deadline, stop using a faulted client, and fence
events across process/load transitions. Route only fully qualified
`X4AuthorityShipRegistry.*` events to this adapter, strip that exact prefix,
and ensure it is the exclusive consumer issuing requests to the MD registry.
Normalize MD index and count values to Lua numbers only after verifying exact,
finite, integral representation within the safe integer range. Never convert
an actor ID through a rounded Lua number. `issue(screen, control, params)` must
return exactly true only when dispatch is confirmed; a wrapper must treat a
nil return from an underlying API as unconfirmed, not as proof of success.
Event delivery must be asynchronous.
The caller provides local actor validity, a stable process-local key and a
conversion to an MD-compatible actor. Both original and converted actor keys
must match. A resolved actor is local and must never be used as a wire ID.

The one-request methods are `initialize()`, `status()`, `enroll(actor)`, and
`resolve(index)`, called with Lua's colon syntax. Completion is delivered through
`complete(operation, value)`, which must return true: `Initialize` returns the
epoch, `Status` returns `{epoch=..., count=...}`, `Enroll` returns an index, and
`Resolve` returns a local actor. The methods return true when dispatched, or
false and a reason when refused. `state()` reports `idle`, `pending`, `failed`,
or `closed`; `close()` discards pending state. An error, unexpected event,
overlap, timeout, invalid or changed actor, bad clock, failed callback or
uncertain dispatch stops the adapter. There are no automatic retries.
`Initialize` is for a fresh, uninitialized MD cue only; the cue is one-shot and
cannot be assumed to initialize again after a refusal or reload. Initialization
timing, persisted registry readiness, and any required fencing belong to the
caller. Injected callbacks must not re-enter the client; a change to client
state during a callback invalidates the operation.

The deadline is checked after dispatch, before completion, and after the
completion callback returns. Callbacks cannot be interrupted: the timeout
detects an overrun only when control returns. A completion callback is therefore
provisional and must not commit external effects; its caller may use the result
only after `on_event` returns true. If the callback exceeds the deadline, the
adapter returns false and faults, but cannot undo effects already performed by
that callback. Actor conversion before a request is dispatched is outside the
request deadline and likewise cannot be preempted.

**Correlation limit:** the existing MD responses do not include a request ID.
An unexpected event while idle, a late event after timeout, and wrong response
types are rejected. However, a delayed duplicate of the expected event from an
earlier request is indistinguishable from the response to a new request of the
same type. Serialization and a new adapter do not remove that ambiguity. The
caller must not use this adapter as a reliably correlated production protocol;
that requires an independently validated correlation or fencing mechanism.
None of the API establishes cross-instance binding, creation/destruction
coverage, multiplayer admission, or gameplay.
